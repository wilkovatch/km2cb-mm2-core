-- Traffic lights of the roads (the startTrafficLight and endTrafficLight parameters).
--
-- Each road type describes the corners where its lights can stand, with late definitions of the "common" category:
-- startTrafficLightPosition and invertedStartTrafficLightPosition at its start, endTrafficLightPosition and
-- invertedEndTrafficLightPosition at its end (the first one of each pair is the default side).
--
-- A light stands on the default corner of its own road, or, with "trafficLightOnOppositeRoad" or a road shift, on a
-- corner of another road of the same intersection.

local M = {}

local function capitalized(s)
    return s:sub(1, 1):upper() .. s:sub(2)
end

-- the default and the inverted corner of a road at one of its ends ("start" or "end")
local function corners(vars, side)
    return vars[side .. "TrafficLightPosition"], vars["inverted" .. capitalized(side) .. "TrafficLightPosition"]
end

local function position(v, ctx, side)
    local own = v[side .. "TrafficLightPosition"]
    local shift = v[side .. "TrafficLightRoadIdxAdj"]
    local opposite = v.trafficLightOnOppositeRoad
    if not opposite and shift == 0 then return own end
    local intersection = ctx:intersection(side)
    if intersection == nil then return own end

    -- the point on the other side of the intersection, in front of the road
    local across = v[side .. "Dir"] * (own:distance(v[side .. "IntersectionPosition"]) * 2)
    local target = side == "start" and own - across or own + across

    -- with "trafficLightOnOppositeRoad", the road with the corner nearest to that point (the first one if equal)
    local selfIndex = intersection.selfIndex
    local chosen = selfIndex
    if opposite then
        local bestScore = -math.huge
        for i = 1, intersection.roadCount do
            local road = intersection:road(i)
            if not road.isSelf then
                local a, b = corners(road.vars, road.atStart and "start" or "end")
                local score = 1 / math.min(target:distance(a), target:distance(b))
                if score > bestScore then
                    bestScore = score
                    chosen = i
                end
            end
        end
    end

    -- then shifted clockwise by the road shift parameter
    local road = intersection:road(chosen + shift)
    if road.isSelf then return own end
    local roadSide = road.atStart and "start" or "end"
    local a, b = corners(road.vars, roadSide)
    local da, db = target:distance(a), target:distance(b)
    local inverted = v[side .. "TrafficLightOppInv"]
    local corner
    if (inverted and da > db) or (not inverted and da < db) then corner = a else corner = b end
    -- moved towards the center of the intersection
    local center = road.vars[roadSide .. "IntersectionPosition"]
    return corner + (center - corner):normalize() * v[side .. "TrafficLightInOffset"]
end

function M.startCondition(v)
    return v.hasStartIntersection and v.backwardLanes > 0 and v.start_rule == 1
end

function M.endCondition(v)
    return v.hasEndIntersection and v.forwardLanes > 0 and v.end_rule == 1
end

-- index in the model options: the first model for a single lane, the second one for more
function M.startMeshIndex(v)
    return v.backwardLanes <= 1 and 0 or 1
end

function M.endMeshIndex(v)
    return v.forwardLanes <= 1 and 0 or 1
end

function M.startPosition(v, ctx)
    return position(v, ctx, "start")
end

function M.endPosition(v, ctx)
    return position(v, ctx, "end")
end

-- the lights face the road they belong to
function M.startRotation(v)
    return vec3(0, v.startDir:signedAngle(v.worldForward, -v.worldUp), 0)
end

function M.endRotation(v)
    return vec3(0, v.endDir:signedAngle(-v.worldForward, -v.worldUp), 0)
end

return M
