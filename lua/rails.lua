local M = {}

-- The rails are the RAILC attributes of the rooms: they flag edges of the perimeter of a room, so their points go only on
-- the perimeter of one PSDL terrain patch, road or intersection, their room (the "room" reference, the ownerReference of
-- the type, set by the first point; when it is on several of them the user chooses it): on the perimeter points of the
-- patch, or on the anchors along the road or intersection (not on the ground, the internal points of the patches, the
-- segments between two points, or the ends of the roads). ctx.owner is the room the target is checked for, with the role
-- the target has in it. The spans follow the perimeter of the room only, and the exporter puts the rail in its room.
local function onPerimeter(owner)
    if owner == nil or owner.type ~= "psdl" then return false end
    if owner.kind == "terrainPatch" then return owner.role == "perimeter" end
    if owner.kind == "road" or owner.kind == "intersection" then return owner.role == "edge" end
    return false
end

function M.acceptTarget(_, ctx)
    local kind = ctx.target.kind
    if kind ~= "point" and kind ~= "anchor" then return false end
    return onPerimeter(ctx.owner)
end

return M
