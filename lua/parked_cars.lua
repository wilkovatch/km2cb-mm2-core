local M = {}

-- The game chooses the cars of the parked car rows by itself (see "Parked cars" in AGENTS.md): for each slot of a path it
-- creates one of the models or nothing. So the models here are only an example, and a slot without one is still exported.
local MODELS = { "geometry/giz_pcar01_l.pkg", "geometry/giz_pcar02_l.pkg", "geometry/giz_pcar03_l.pkg" }
-- the exporter gives a row a vertex at each slot, the game needs a span of at least 5 m
local MIN_SPACING, MAX_SPACING = 5.25, 100

-- A point element uses a short, horizontal reference line to give its single slot a position and heading.
function M.singleGeometry(_, ctx)
    local center = ctx.points.center
    local yaw = math.rad((ctx.rotations.center or vec3(0, 0, 0)).y)
    local forward = vec3(math.sin(yaw), 0, math.cos(yaw))
    local right = vec3(math.cos(yaw), 0, -math.sin(yaw)) * 0.5
    return { propLines = {
        { container = "main", startBound = { center + right, center + right + forward },
          endBound = { center - right, center - right + forward } }
    } }
end

function M.single(_, ctx)
    local line = ctx.sample(0.5, 0)
    -- Always show an example, even though the game may leave the slot empty.
    return { { position = line.position, forward = line.tangent, model = MODELS[1] } }
end

function M.row(v, ctx)
    -- stock: rand() % 3, 0 leaves the slot empty and the other two give the two models
    -- MM2Hook (UseAllParkedCars): rand() % 4, 0 leaves the slot empty and the other three give the three models
    local hook = v._GLOBAL_assumeMM2Hook
    local odds, models = hook and 4 or 3, hook and 3 or 2
    local spacing = math.min(math.max(v.elemDistance, MIN_SPACING), MAX_SPACING)
    local direction = v.reverse and 1 or -1
    -- a road row follows the traffic of the nearest lanes, which left-hand traffic turns around (a prop line has no lanes)
    if v._GLOBAL_driveOnLeft and not ctx.placer then direction = -direction end
    local result = {}
    local z = v.start
    while z <= ctx.length - v["end"] do
        local line = ctx.sample(v.xPos, z)
        local placement = { position = line.position, forward = line.forward * direction }
        if ctx.random() * odds >= 1 then placement.model = MODELS[1 + math.floor(ctx.random() * models)] end
        result[#result + 1] = placement
        z = z + spacing
    end
    return result
end

return M
