local M = {}

-- The sidewalks of the intersections (the builder wiki Core-Intersections, "Sidewalk segments").

-- The road-style UV of the sidewalks (fixSidewalksUV) needs sections with 4 distinct sides: it is enabled only while the
-- outer side of the sidewalks has the same segments as the inner one. A sidewalk overriding them with different ones has
-- the normal UV anyway (sidewalkSidesMatch in components/intersectionSidewalk.json, sidewalksMatch in the exporter).
function M.roadStyleUVAvailable(_, ctx)
    local state = ctx.element.state
    local inner = state.sidewalkSegments or 1
    local outer = state.sidewalkOuterSegments or 0
    return (outer <= 0 or outer == inner) and state.sidewalkOuterSkipsCrosswalks ~= true
end

return M
