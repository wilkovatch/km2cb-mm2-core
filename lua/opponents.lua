local M = {}

-- The waypoints of an opponent (the points of its spline, after the car at the start). The game replaces every waypoint
-- but the last one with the first BAI intersection of its room, and leaves it undefined in any other room (see
-- docs/agents/races-and-state.md), so these go only on the centers of the intersections (intersectionTargets), which
-- they follow. The last one is the finish, a position, which can go anywhere. ctx.index is nil when the type is asked in
-- general: as for a waypoint. A seamless intersection is refused: its two roads can be a single BAI road, and a
-- waypoint there is never needed (the opponent follows the road through it).
function M.acceptTarget(_, ctx)
    if ctx.index ~= nil and ctx.index == ctx.count then return true end
    local intersection = ctx.target.intersection
    return intersection ~= nil and not intersection.seamless
end

return M
