local M = {}

function M.canGenerateRails(_, ctx)
    local count = 0
    local seen = {}
    for _, road in ipairs(ctx.neighbors) do
        if road.kind == "road" and road.state.cableCarLine and not seen[road.id] then
            seen[road.id] = true
            count = count + 1
        end
    end
    return count >= 2
end

-- Single decal: a quad as the strips of the spline decals (the first pair of vertices at the start, U 1 then 0), as wide
-- as the scale X of the point and as long as its scale Z, rotated by the point (the euler angles are applied as Z, X, Y
-- in program coordinates), 0.01 m above it. V at the far pair is the length in tiles, rounded as the game does.
local function rotateEuler(p, e)
    local x, y, z = p.x, p.y, p.z
    local c, s = math.cos(math.rad(e.z)), math.sin(math.rad(e.z))
    x, y = c * x - s * y, s * x + c * y
    c, s = math.cos(math.rad(e.x)), math.sin(math.rad(e.x))
    y, z = c * y - s * z, s * y + c * z
    c, s = math.cos(math.rad(e.y)), math.sin(math.rad(e.y))
    x, z = c * x + s * z, -s * x + c * z
    return vec3(x, y, z)
end

function M.single(_, ctx)
    local center = ctx.points.center
    local rotation = ctx.rotations.center or vec3(0, 0, 0)
    local scale = ctx.scales.center or vec3(1, 1, 1)
    local lift = vec3(0, 0.01, 0)
    local width, length = math.abs(scale.x), math.abs(scale.z)
    local tiles = math.floor(length / math.max(width, 0.0001) + 0.5)
    local mesh = { texture = "texture", vertices = {}, uvs = {}, triangles = { 0, 2, 1, 1, 2, 3 } }
    local corners = {}
    for i, c in ipairs({ { -0.5, -0.5, 1, 0 }, { 0.5, -0.5, 0, 0 }, { -0.5, 0.5, 1, tiles }, { 0.5, 0.5, 0, tiles } }) do
        local p = center + rotateEuler(vec3(c[1] * scale.x, 0, c[2] * scale.z), rotation)
        corners[i] = p
        mesh.vertices[i] = p + lift
        mesh.uvs[i] = vec2(c[3], c[4])
    end
    return {
        meshes = { mesh },
        lines = { { points = { corners[1], corners[2], corners[4], corners[3] }, closed = true, color = "yellow", heightOffset = 0.05 } }
    }
end

return M
