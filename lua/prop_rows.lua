local M = {}

-- The rows of props of the MM2 prop rules: a prop every elemDistance metres along the lines, up to maxNumber.
-- The positions must not change from the ones of existing cities, so the random numbers (shared with the other rows of the
-- element: rnd, not ctx.random) are taken in this order, also when the row ends there: across, then the mesh. The sums are
-- in single precision, as in the expressions the rows used to be defined with.
local UP = vec3(0, 1, 0)

local function row(ctx, start, distance, maxNumber, stop, across, model, direction)
    local result, count = {}, 0
    if maxNumber == 0 then maxNumber = 9999 end
    local limit = ctx.limit
    local sample = ctx.sample
    local i, z = 0, start
    while true do
        local x = across()
        if i > 0 then z = single(z + distance) end
        if not (distance > 0 and i < maxNumber and z <= stop) or i >= limit then break end
        local mesh = model(i)
        if mesh ~= "" then
            local line = sample(x, z)
            count = count + 1
            result[count] = { position = line.position, forward = direction(line), model = mesh }
        end
        i = i + 1
    end
    return result
end

local function forward(line)
    return line.forward
end

function M.line(v, ctx)
    local x, mesh, angle = v.xPos, ctx.parameters.mesh or "", v.rotationAngle
    return row(ctx, v.start, v.elemDistance, v.maxNumber, single(ctx.length - v["end"]),
        function() return x end, function() return mesh end,
        function(line) return line.forward:rotate(UP, angle) end)
end

local function random_across(v)
    local minimum, maximum = v.minHorizPos, v.maxHorizPos
    return function() return rnd(minimum, maximum, 0) end
end

-- the mesh of an index given as a number: only the whole part counts
local function mesh_at(meshes, count, index)
    return meshes[math.max(0, math.min(math.floor(index), count - 1)) + 1]
end

function M.custom(v, ctx)
    local meshes = ctx.parameters.meshes
    if meshes == nil or #meshes == 0 then return {} end
    local count, random, angle = #meshes, v.random, v.rotationAngle
    return row(ctx, v.start, v.elemDistance, v.maxNumber, single(ctx.length - v["end"]), random_across(v),
        function(i) return mesh_at(meshes, count, random and rnd(0, count, 0) or i % count) end,
        function(line) return line.forward:rotate(UP, angle) end)
end

function M.psdl(v, ctx)
    local meshes = ctx.parameters.meshes
    if meshes == nil or #meshes == 0 then return {} end
    local count = #meshes
    return row(ctx, v.start, v.elemDistance, v.maxNumber, ctx.length, random_across(v),
        function() return mesh_at(meshes, count, rnd(0, count, 0)) end, forward)
end

-- A pathset line as the game reads it: on each span between two points the step is stretched to fill it, a span shorter
-- than the spacing gets no props, and the X axis of the model lies along the span.
-- Projected on the ground, each prop goes on the ground and the exporter gives the path a point at each one, so each prop
-- has a span of its own. The ground can make it shorter than the step along a sloped span of the spline, but not shorter
-- than the step on the plan: counting the props on the plan, no prop of the game gets lost.
function M.pathset(v, ctx)
    local result, count = {}, 0
    local mesh, distance = ctx.parameters.mesh or "", v.elemDistance
    if distance <= 0 or mesh == "" then return result end
    local limit = ctx.limit
    local edges = ctx.edges()
    for _, edge in ipairs(edges) do
        local counted = edge.length
        if ctx.projected then
            local a, b = edge.sample(0.5, 0).position, edge.sample(0.5, edge.length).position
            counted = math.sqrt((b.x - a.x) ^ 2 + (b.z - a.z) ^ 2)
        end
        local spanProps = math.floor(single(counted / distance))
        if spanProps > 0 then
            local step = single(edge.length / spanProps)
            local z = 0
            for i = 1, math.min(spanProps, limit) do
                local line = edge.sample(0.5, z)
                count = count + 1
                result[count] = { position = line.position, forward = UP:cross(line.tangent), model = mesh }
                z = single(z + step)
            end
        end
    end
    -- without a model: only where the path of the last prop ends, for the exporter
    if ctx.projected and count > 0 then
        local last = edges[#edges]
        result[count + 1] = { position = last.sample(0.5, last.length).position }
    end
    return result
end

return M
