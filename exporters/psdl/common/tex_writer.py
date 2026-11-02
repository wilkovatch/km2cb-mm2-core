"""Writer of Angel Studios .tex textures (the format read by server/texture_formats.py).

Header: u16 width, u16 height, u16 type, u16 mip count, u16 (1), u32 flags, then the mip levels (largest first),
rows in the order they are given. Types written: 17 (RGB, 3 bytes per pixel) and 18 (RGBA, 4 bytes per pixel).
Width and height must be powers of two.
"""
import struct

TYPE_RGB = 17
TYPE_RGBA = 18
FLAGS = 0x00018006  # as in the stock textures


def _halve(pixels, w, h, channels):
    """Box-filtered half size image (flat list of channel values)."""
    res = bytearray()
    w2, h2 = max(1, w // 2), max(1, h // 2)
    for y in range(h2):
        for x in range(w2):
            for c in range(channels):
                s = 0
                n = 0
                for dy in (0, 1):
                    for dx in (0, 1):
                        xx, yy = min(w - 1, 2 * x + dx), min(h - 1, 2 * y + dy)
                        s += pixels[(yy * w + xx) * channels + c]
                        n += 1
                res.append((s + n // 2) // n)
    return res, w2, h2


def write_tex(path, width, height, pixels, alpha=False, mips=3):
    """pixels: bytes of width * height RGB (or RGBA if alpha) values, row by row."""
    channels = 4 if alpha else 3
    if len(pixels) != width * height * channels:
        raise ValueError('expected %d bytes of pixels, got %d' % (width * height * channels, len(pixels)))
    max_mips = 1
    while (width >> max_mips) >= 1 and (height >> max_mips) >= 1 and max_mips < mips:
        max_mips += 1
    with open(path, 'wb') as f:
        f.write(struct.pack('<5HI', width, height, TYPE_RGBA if alpha else TYPE_RGB, max_mips, 1, FLAGS))
        level, w, h = bytearray(pixels), width, height
        for m in range(max_mips):
            f.write(level)
            if m + 1 < max_mips:
                level, w, h = _halve(level, w, h, channels)


def write_image(path, image, mips=3):
    """Writes a PIL image (RGB or RGBA)."""
    alpha = image.mode == 'RGBA'
    if not alpha:
        image = image.convert('RGB')
    write_tex(path, image.size[0], image.size[1], image.tobytes(), alpha, mips)
