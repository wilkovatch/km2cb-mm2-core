local M = {}

-- gizBridge::UpdateMatrix (577620): local -Size.z/2, rotated about X, then the placement
-- frame and the world offset (0,-0.3,0). Banger CG is applied by the mesh placement transform.
-- The game reads Size from the banger data of the model: the size of the mesh here (they match in the stock models),
-- and what the exporter writes for a model without banger data. An element made without a model uses the default of the exporter.
local DEFAULT_MESH, DEFAULT_LENGTH = "geometry/giz_bridge01_l.pkg", 30.000004

-- the mesh is generated from the roads the controls are attached to
function M.canGenerateMesh(_, ctx)
    for _, neighbor in ipairs(ctx.neighbors) do
        if neighbor.kind == "road" then return true end
    end
    return false
end

function M.geometry(v, ctx)
    local a, b = ctx.points.start, ctx.points.finish
    local delta = b - a
    local length = math.sqrt(delta.x^2 + delta.y^2 + delta.z^2)
    local horizontal = math.sqrt(delta.x^2 + delta.z^2)
    local result = { props = {}, lines = {
        { points = { a, b }, color = "cyan", always = true, wideCollider = true }
    } }
    if length < 0.001 or horizontal < 0.001 then return result end
    local mesh, modelLength = ctx.parameters.mesh, ctx.meshSizes.mesh and ctx.meshSizes.mesh.z
    if not mesh or mesh == "" then mesh, modelLength = DEFAULT_MESH, DEFAULT_LENGTH end
    -- a generated model for a road at an angle is longer than its Size.z, the distance of its ends from the hinge line
    if mesh == ctx.parameters.generatedMesh and v.generatedLength > 0 then modelLength = v.generatedLength end
    if not modelLength then return result end -- no size: only the control line
    local angle = v.preview == 2 and 27 or v.preview == 1 and 0 or v.behavior == 3 and 27 or 0
    -- The closed model faces away from the opposite hinge; its negative Z extends into the opening.
    local function leaf(origin, other)
        local z = (origin - other) / length
        local up = vec3(-z.y * z.x, 1 - z.y^2, -z.y * z.z) / (horizontal / length)
        local theta = math.rad(angle)
        local forward = z * math.cos(theta) - up * math.sin(theta)
        result.props[#result.props + 1] = {
            model = mesh, meshTransform = true,
            position = origin - forward * (modelLength * 0.5) + vec3(0, -0.3, 0),
            -- math.atan takes a single argument in this Lua: the direction needs atan2
            rotation = vec3(math.deg(math.asin(math.max(-1, math.min(1, -forward.y)))), math.deg(math.atan2(forward.x, forward.z)), 0)
        }
    end
    leaf(a, b)
    if v.paired then leaf(b, a) end
    return result
end

return M
