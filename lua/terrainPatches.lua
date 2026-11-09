-- The geometry of the terrain patches: the bottom wall under the patch (forceBottom), as the one of the elevated roads
-- (rail_wall_bottom): the surface again, 1 m lower and facing down, with the bottomTexture. The PSDL can't draw it under
-- a patch, so the exporter writes it as an unlit PKG mesh (the last submesh of the patch, see get_patch in
-- exporters/psdl/json_processor.py).
local M = {}

local DEPTH = 1.0

function M.geometry(v, ctx)
    local texture = ctx.parameters.bottomTexture
    if not v.forceBottom or texture == nil or texture == "" then return {} end
    local surface, down = ctx.surface, vec3(0, -DEPTH, 0)
    local vertices, triangles = {}, {}
    for i, p in ipairs(surface.vertices) do vertices[i] = p + down end
    local t = surface.triangles
    for i = 1, #t - 2, 3 do
        -- the other way round: seen from below
        triangles[#triangles + 1] = t[i]
        triangles[#triangles + 1] = t[i + 2]
        triangles[#triangles + 1] = t[i + 1]
    end
    return { meshes = { { texture = "bottomTexture", vertices = vertices, uvs = surface.uvs, triangles = triangles } } }
end

return M
