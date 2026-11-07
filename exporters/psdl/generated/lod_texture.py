"""The low LOD texture of a road, generated from its textures and widths (the road flag generateLodTexture).

The game draws the whole width of the road with one square texture at the lowest level of detail. The stock ones (e.g.
r6_lo_f) show, across the road, a sidewalk, half of the road, the divider, the other half and the other sidewalk, in
proportion to their widths. Along the road each texture tiles as long as it is wide, as in the game.
"""
import hashlib
import os
from pathlib import Path
import re
import struct
import sys

import numpy as np
from PIL import Image

from generated import CORE, GenerationError
from writers.tex_writer import write_image
from utils import state_bool, state_int, state_val

if str(CORE / 'server') not in sys.path:
    sys.path.append(str(CORE / 'server'))
from texture_formats import read_file

SIZE = 64  # as the stock low LOD textures
OVERSAMPLING = 8  # samples per side of each pixel, so that the thin lane markings fade instead of disappearing
BASE_NAME_LENGTH = 17  # the file name with _lod_<hash> and _fa stays within 31 characters, the limit of the names of the decals
VARIANTS = ['_fa']  # the stock road textures also have a darker version with this suffix
# what the texture depends on: the roads with the same values share it
INPUTS = ('hasSidewalks', 'flatSidewalk', 'roadWidth', 'totalWidth', 'divider', 'dividerWidth', 'dividerParam',
          'texture0', 'texture1', 'texture3', 'texture4')


def enabled(state):
    # only the double roads have a low LOD texture (the exporter writes just the main texture of the others), and it
    # needs their road texture
    return state_bool(state, 'generateLodTexture') and state_bool(state, 'isDouble') and bool(state_val(state, 'texture1'))


def road_bands(state):
    """The bands across the road: (width, texture parameter, tiles along the road per meter, tiles across, flipped)."""
    # as the road type: without real sidewalks the texture covers only the road (the shoulders are not part of it)
    has_sidewalks = state_bool(state, 'hasSidewalks')
    road = float(state_val(state, 'roadWidth' if has_sidewalks else 'totalWidth', 0))
    sidewalk = (float(state_val(state, 'totalWidth', 0)) - road) * 0.5 if has_sidewalks and not state_bool(state, 'flatSidewalk') else 0
    divider_type = state_int(state, 'divider')
    divider = float(state_val(state, 'dividerWidth', 0)) if divider_type > 0 else 0
    half = (road - divider) * 0.5
    if half <= 0 or sidewalk < 0:
        raise GenerationError('LOD_TEXTURE_ERROR_WIDTHS')
    bands = []
    if sidewalk > 0:
        bands.append((sidewalk, 'texture0', 1 / sidewalk, 1, False))
    bands.append((half, 'texture1', 1 / half, 1, False))
    bands += divider_bands(divider_type, divider, float(state_val(state, 'dividerParam', 0)))
    bands.append((half, 'texture1', 1 / half, 1, True))
    if sidewalk > 0:
        bands.append((sidewalk, 'texture0', 1 / sidewalk, 1, True))
    return bands


def divider_bands(divider_type, width, param):
    # seen from above (see the divider components): flat, a strip repeating param times across; elevated and wedged, a
    # center strip between two strips as wide as param (elevated) or 0.5 m (wedged)
    if divider_type == 0 or width <= 0:
        return []
    if divider_type == 1:
        tiles = param if param > 0 else 1
        return [(width, 'texture3', tiles / width, tiles, False)]
    side = min(max(param, 0) if divider_type == 2 else 0.5, width * 0.5)
    center = width - 2 * side
    bands = [(center, 'texture4', 1 / center, 1, False)] if center > 0 else []
    if side > 0:
        bands = [(side, 'texture3', 1 / side, 1, False)] + bands + [(side, 'texture3', 1 / side, 1, True)]
    return bands


def compose(bands, images):
    """The texture from the bands and the images of the textures (arrays of rows of RGB values, from the top)."""
    size = SIZE * OVERSAMPLING
    total = sum(band[0] for band in bands)
    res = np.zeros((size, size, 3), np.uint8)
    position = 0
    start = 0
    for width, parameter, along, across, flipped in bands:
        position += width
        end = round(position / total * size)
        image = images[parameter]
        # a whole number of tiles along the road, so that the texture repeats without seams
        tiles = max(1, round(along * total))
        rows = ((np.arange(end - start) + 0.5) / (end - start) * across * image.shape[0]).astype(int) % image.shape[0]
        columns = ((np.arange(size) + 0.5) / size * tiles * image.shape[1]).astype(int) % image.shape[1]
        if flipped:
            rows = rows[::-1]
        res[start:end] = image[rows][:, columns]
        start = end
    return Image.fromarray(res).resize((SIZE, SIZE), Image.BOX)


def find_file(path, folders):
    # the file of a texture parameter: an absolute path, or relative to the folders (the names can differ in case from
    # the files, as the game reads them on case-insensitive file systems)
    path = path.replace('\\', '/')
    if os.path.isabs(path):
        return path if os.path.isfile(path) else None
    for folder in folders:
        current = folder
        for part in path.split('/'):
            candidate = os.path.join(current, part)
            if not os.path.exists(candidate) and os.path.isdir(current):
                candidate = next((os.path.join(current, e) for e in os.listdir(current) if e.lower() == part.lower()), candidate)
            current = candidate
        if os.path.isfile(current):
            return current
    return None


def read_image(path):
    if path.lower().endswith('.tex'):
        # see texture_formats.read_file: the size and channels, then the largest mip level, from the top row
        data = read_file(path)
        width, height, channels = struct.unpack_from('<3i', data, 4)
        return np.frombuffer(data, np.uint8, width * height * channels, 20).reshape(height, width, channels)[:, :, :3]
    return np.asarray(Image.open(path).convert('RGB'))


def load_images(state, folders, parameters, suffix=''):
    """The images of the parameters, the ones of the variant with the suffix if they exist. None if a texture needed is missing."""
    res = {}
    for parameter in parameters:
        path = state_val(state, parameter)
        found = None
        if path:
            stem, extension = os.path.splitext(path)
            found = (find_file(stem + suffix + extension, folders) if suffix else None) or find_file(path, folders)
        if found is not None:
            res[parameter] = read_image(found)
        elif parameter in ('texture0', 'texture1'):
            return None
    # a divider without a texture takes the color of the road, the rest of the bands are not affected
    for parameter in parameters:
        if parameter not in res:
            res[parameter] = res['texture1'].mean((0, 1), keepdims=True).astype(np.uint8)
    return res


def generate(state, out, folders):
    """Writes the texture of the road in the texture folder of out (an OutputRoot), returns its path relative to it."""
    key = ('lodTexture',) + tuple(str(state_val(state, name)) for name in INPUTS)
    if key in out.memo:
        return out.memo[key]
    bands = road_bands(state)
    parameters = sorted({band[1] for band in bands})
    images = load_images(state, folders, parameters)
    if images is None:
        raise GenerationError('LOD_TEXTURE_ERROR_MISSING')
    image = compose(bands, images)
    # named after its contents: the roads with the same result share one texture, as the textures of a city are limited
    road_name = re.sub(r'[^a-z0-9_]', '_', Path(state_val(state, 'texture1')).stem.lower())[:BASE_NAME_LENGTH]
    name = road_name + '_lod_' + hashlib.sha1(image.tobytes()).hexdigest()[:6]
    # the rows of the .tex files go from the bottom of the image, the stock low LOD textures have no mip levels
    write_image(out.path('texture/' + name + '.tex'), image.transpose(Image.FLIP_TOP_BOTTOM), 1)
    for suffix in VARIANTS:
        stem, extension = os.path.splitext(state_val(state, 'texture1'))
        if find_file(stem + suffix + extension, folders) is None:
            continue
        variant = compose(bands, load_images(state, folders, parameters, suffix))
        write_image(out.path('texture/' + name + suffix + '.tex'), variant.transpose(Image.FLIP_TOP_BOTTOM), 1)
    out.memo[key] = 'texture/' + name + '.tex'
    return out.memo[key]
