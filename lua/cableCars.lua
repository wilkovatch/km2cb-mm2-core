local M = {}

-- The rail decals of the cable cars (the extras cableCarRails of the psdl roads and intersections, see the builder wiki
-- Core-Extras): strips of the rail texture along the rails of the roads (their traffic lanes of type 3 and 4) and across
-- the intersections, along the path the cars take in game (exporters/psdl/traffic/rails.py, reverse-engineered from the
-- game, see docs/agents/trains-and-boats.md, "Cable cars"; keep the two in sync), with crossing squares where two rails
-- cross in an intersection. Each strip is exported as its pairs of points across it (export.decals), the exporter
-- writes each two consecutive pairs as a decal (exporters/psdl/decals.py).

M.HALF_LENGTH = 4.36 -- the cars leave a road this far before its end (half the length of va_cablecar_f)
local LIFT = 0.01 -- the strips are drawn this much above the road, as the game draws the decals
local MAX_PIECE = 12.0 -- the longest piece of strip (a decal is drawn only with the room of its start)
local CURVE_STEP = 2.0 -- the length of the segments of the curves through the intersections
local RAIL_TYPES = { [3] = true, [4] = true }
local RAIL_TEXTURE = "texture/r4i_rails_f.tex" -- the textures of the stock San Francisco rails, when the parameters have none
local CROSSING_TEXTURE = "texture/r4i_railsX_f.tex"

local function flat(v)
    return vec3(v.x, 0, v.z)
end

local function normalized(v)
    local m = v:magnitude()
    if m < 1e-6 then return vec3(0, 0, 0) end
    return v * (1 / m)
end

-- the horizontal vector to the right of a direction (left-handed, y up)
local function rightOf(d)
    return normalized(vec3(d.z, 0, -d.x))
end

local function reversed(list)
    local res = {}
    for i = #list, 1, -1 do res[#res + 1] = list[i] end
    return res
end

-- the centre line of a road: the middle of the first and last vertex of each section (as the centre of the BAI, midway
-- between the outer edges)
local function centreLine(sections)
    local res = {}
    for i, s in ipairs(sections) do res[i] = (s[1] + s[#s]) * 0.5 end
    return res
end

-- the rails of a road, from its start to its end: forward (the cars go from its start to its end, the rail on the right
-- of the sections, the left side of the BAI) and backward (the other one), nil if it hasn't one of each with a point
-- per section (as traffic/paths.py)
function M.roadRails(sections, lanes)
    if sections == nil or #sections < 2 then return nil end
    local first = sections[1]
    local a = first[1]
    local across = first[#first] - a
    local middle = across:dot(across) / 2
    local forward, backward = {}, {}
    for _, lane in ipairs(lanes or {}) do
        if lane.type ~= nil and RAIL_TYPES[lane.type] and #lane.points == #sections then
            if (lane.points[1] - a):dot(across) < middle then backward[#backward + 1] = lane.points
            else forward[#forward + 1] = lane.points end
        end
    end
    if #forward ~= 1 or #backward ~= 1 then return nil end
    return { forward = forward[1], backward = backward[1] }
end

-- the next road of a cable car (traffic/rails.py, next_tram_road): flags, whether each road of the intersection has
-- rails, in order; own, the index of the road it comes from. Its own road at the end of a line, nil if there is none
function M.nextRoad(flags, own)
    local count = 0
    for _, f in ipairs(flags) do if f then count = count + 1 end end
    if count == 1 then return own end
    local need = ({ [2] = 1, [4] = 2 })[count]
    if need == nil then return nil end
    local n, i, found = #flags, own, 0
    for _ = 1, n do
        i = i % n + 1
        if flags[i] then
            found = found + 1
            if found == need then return i end
        end
    end
    return nil
end

-- whether the cars go on through an intersection with these roads (with 2 or 4 of them with rails)
local function goesOn(count)
    return count == 2 or count == 4
end

-- the point where the car leaves a rail (in the order it goes along it) and its direction there: on the last segment,
-- half the car before the end, measured on the centre line (traffic/rails.py, curve_start)
local function leaving(rail, centre)
    local n = #rail
    local a, b = rail[n - 1], rail[n]
    local length = (centre[n] - centre[n - 1]):magnitude()
    if length < 1e-6 then return b, normalized(b - a), 0 end
    return a + (b - a) * ((length - M.HALF_LENGTH) / length), normalized(centre[n] - centre[n - 1]), (b - a):magnitude() * M.HALF_LENGTH / length
end

-- the path through the intersection (traffic/rails.py, transition_curve): a Hermite in x and z with the tangents scaled
-- by |dx| + |dz|, the height linear
local function transition(p0, d0, p1, d1)
    local scale = math.abs(p0.x - p1.x) + math.abs(p0.z - p1.z)
    local t0, t1 = d0 * scale, d1 * scale
    local n = math.max(2, math.ceil(flat(p1 - p0):magnitude() / CURVE_STEP))
    local res = {}
    for k = 0, n do
        local t = k / n
        local h00, h10, h01, h11 = 2*t^3 - 3*t^2 + 1, t^3 - 2*t^2 + t, -2*t^3 + 3*t^2, t^3 - t^2
        local p = p0 * h00 + t0 * h10 + p1 * h01 + t1 * h11
        res[#res + 1] = vec3(p.x, p0.y + (p1.y - p0.y) * t, p.z)
    end
    return res
end

-- Polylines

local function lengths(points)
    local res = { 0 }
    for i = 2, #points do res[i] = res[i - 1] + (points[i] - points[i - 1]):magnitude() end
    return res
end

local function pointAt(points, cum, s)
    for i = 2, #points do
        if s <= cum[i] or i == #points then
            local l = cum[i] - cum[i - 1]
            local t = l > 1e-9 and (s - cum[i - 1]) / l or 0
            return points[i - 1] + (points[i] - points[i - 1]) * t
        end
    end
    return points[1]
end

-- the part of a polyline between the distances s0 and s1 from its start
local function part(points, cum, s0, s1)
    local res = { pointAt(points, cum, s0) }
    for i = 2, #points - 1 do
        if cum[i] > s0 and cum[i] < s1 then res[#res + 1] = points[i] end
    end
    res[#res + 1] = pointAt(points, cum, s1)
    return res
end

-- the parts of a polyline left out of the intervals {s0, s1} (sorted by s0, not overlapping)
local function without(points, cuts)
    local cum = lengths(points)
    local total = cum[#cum]
    local res, s = {}, 0
    for _, c in ipairs(cuts) do
        if c[1] > s + 0.01 then res[#res + 1] = part(points, cum, s, math.min(c[1], total)) end
        s = math.max(s, c[2])
    end
    if total > s + 0.01 then res[#res + 1] = part(points, cum, s, total) end
    return res
end

-- the polyline shortened by d at its start (atStart) or at its end
local function trimmed(points, d, atStart)
    local cum = lengths(points)
    local total = cum[#cum]
    if d >= total - 0.01 then return nil end
    if atStart then return part(points, cum, d, total) end
    return part(points, cum, 0, total - d)
end

-- Strips

-- the pairs of points across a strip of the given width along a polyline (left then right of its direction), at its
-- points (with mitered sides) and every MAX_PIECE at most between them
local function stripPairs(points, width)
    local n = #points
    if n < 2 then return {} end
    local rights = {}
    for i = 1, n - 1 do rights[i] = rightOf(points[i + 1] - points[i]) end
    local function sideAt(i)
        if i == 1 then return rights[1] end
        if i == n then return rights[n - 1] end
        local r = normalized(rights[i - 1] + rights[i])
        local c = math.max(0.5, r:dot(rights[i]))
        return r * (1 / c)
    end
    local half = width / 2
    local pairs = {}
    local function add(p, r)
        pairs[#pairs + 1] = p - r * half
        pairs[#pairs + 1] = p + r * half
    end
    for i = 1, n - 1 do
        local a, b = points[i], points[i + 1]
        local pieces = math.max(1, math.ceil((b - a):magnitude() / MAX_PIECE))
        if i == 1 then add(a, sideAt(1)) end
        for k = 1, pieces - 1 do add(a + (b - a) * (k / pieces), rights[i]) end
        add(b, sideAt(i + 1))
    end
    return pairs
end

-- the mesh of strips given as pairs (the texture parameter of the element), each two consecutive pairs as its own tiles,
-- as the game draws them (V up to the length in widths, rounded, at least 1)
local function stripMesh(texture, strips, width)
    local mesh = { texture = texture, vertices = {}, uvs = {}, triangles = {} }
    local lift = vec3(0, LIFT, 0)
    for _, pairs in ipairs(strips) do
        for i = 1, #pairs - 3, 2 do
            local a0, b0, a1, b1 = pairs[i], pairs[i + 1], pairs[i + 2], pairs[i + 3]
            local length = ((a1 + b1) * 0.5 - (a0 + b0) * 0.5):magnitude()
            local tiles = math.max(1, math.floor(length / math.max(width, 0.0001) + 0.5))
            local o = #mesh.vertices
            for k, v in ipairs({ { a0, 1, 0 }, { b0, 0, 0 }, { a1, 1, tiles }, { b1, 0, tiles } }) do
                mesh.vertices[o + k] = v[1] + lift
                mesh.uvs[o + k] = vec2(v[2], v[3])
            end
            for _, t in ipairs({ 0, 2, 1, 1, 2, 3 }) do mesh.triangles[#mesh.triangles + 1] = o + t end
        end
    end
    return mesh
end

-- parts: {parameters, parameter (of the texture), fallback (the texture without a value), width, strips}
local function result(parts)
    local meshes, decals = {}, {}
    for _, p in ipairs(parts) do
        local value = p.parameters[p.parameter]
        local set = value ~= nil and value ~= ""
        p.texture = set and value or p.fallback
        if #p.strips > 0 then
            -- the preview takes the texture of the parameter, or the default texture by its path
            meshes[#meshes + 1] = stripMesh(set and p.parameter or p.fallback, p.strips, p.width)
            for _, pairs in ipairs(p.strips) do
                if #pairs >= 4 then decals[#decals + 1] = { texture = p.texture, pairs = pairs } end
            end
        end
    end
    return { meshes = meshes, export = { decals = decals } }
end

local function railWidth(parameters)
    local w = tonumber(parameters.cableCarRailWidth) or 0
    return w > 0 and w or 2.0
end

-- Road

-- whether the cars go on through the intersection at an end of a road with its rails drawn by the intersection (so the
-- road leaves the rail arriving there to it from where the cars leave the road)
local function joinedAt(view)
    if view == nil or not view.parameters.cableCarRails then return false end
    local count = 0
    for i = 1, view.roadCount do
        if view:road(i).parameters.cableCarLine then count = count + 1 end
    end
    return goesOn(count)
end

function M.road(_, ctx)
    local rails = M.roadRails(ctx.sections, ctx.lanes)
    if rails == nil then return nil end
    local width = railWidth(ctx.parameters)
    local centre = centreLine(ctx.sections)
    local strips = {}
    -- forward: the cars arrive at the end; backward: at the start
    for _, r in ipairs({ { rails.forward, "end" }, { rails.backward, "start" } }) do
        local rail = r[1]
        if joinedAt(ctx.road:intersection(r[2])) then
            local travel = r[2] == "end" and rail or reversed(rail)
            local _, _, d = leaving(travel, r[2] == "end" and centre or reversed(centre))
            rail = trimmed(rail, d, r[2] == "start")
        end
        if rail ~= nil then strips[#strips + 1] = stripPairs(rail, width) end
    end
    return result({ { parameters = ctx.parameters, parameter = "cableCarRailTexture", fallback = RAIL_TEXTURE, width = width, strips = strips } })
end

-- Intersection

-- the segment intersection of ab and cd in x and z: the fraction along ab, nil if they don't cross
local function crossing(a, b, c, d)
    local rx, rz = b.x - a.x, b.z - a.z
    local sx, sz = d.x - c.x, d.z - c.z
    local den = rx * sz - rz * sx
    if math.abs(den) < 1e-9 then return nil end
    local qx, qz = c.x - a.x, c.z - a.z
    local t = (qx * sz - qz * sx) / den
    local u = (qx * rz - qz * rx) / den
    if t < 0 or t > 1 or u < 0 or u > 1 then return nil end
    return t
end

function M.intersection(_, ctx)
    local roads = {}
    local flags = {}
    for i, road in ipairs(ctx.roads) do
        local rails = road.parameters.cableCarLine and M.roadRails(road.sections, road.lanes) or nil
        roads[i] = { road = road, rails = rails, centre = rails and centreLine(road.sections) }
        flags[i] = road.parameters.cableCarLine == true
    end
    local count = 0
    for _, f in ipairs(flags) do if f then count = count + 1 end end
    if not goesOn(count) then return nil end
    local width = railWidth(ctx.parameters)

    -- the paths of the cars from each road with rails into its next one
    local curves = {}
    for i, r in ipairs(roads) do
        local j = flags[i] and M.nextRoad(flags, i) or nil
        local nr = j and roads[j]
        if r.rails ~= nil and nr ~= nil and nr.rails ~= nil and j ~= i then
            -- arriving at its start: the backward rail (going back to the start); at its end: the forward one
            local rail = r.road.atStart and reversed(r.rails.backward) or r.rails.forward
            local centre = r.road.atStart and reversed(r.centre) or r.centre
            -- leaving from its start: the forward rail; from its end: the backward one (going back)
            local next = nr.road.atStart and nr.rails.forward or reversed(nr.rails.backward)
            local nextCentre = nr.road.atStart and nr.centre or reversed(nr.centre)
            local p0, d0 = leaving(rail, centre)
            local d1 = normalized(nextCentre[2] - nextCentre[1])
            curves[#curves + 1] = { line = math.min(i, j) * 1000 + math.max(i, j), points = transition(p0, d0, next[1], d1), cuts = {} }
        end
    end

    -- the crossings of the rails of two lines, cut out of both and covered by a square of the crossing texture
    local squares, centres = {}, {}
    if not ctx.parameters.cableCarHideCrossings then
        local half = width / 2
        for a = 1, #curves do
            for b = a + 1, #curves do
                local ca, cb = curves[a], curves[b]
                if ca.line ~= cb.line then
                    local cumA, cumB = lengths(ca.points), lengths(cb.points)
                    for i = 1, #ca.points - 1 do
                        for k = 1, #cb.points - 1 do
                            local t = crossing(ca.points[i], ca.points[i + 1], cb.points[k], cb.points[k + 1])
                            if t ~= nil then
                                local u = crossing(cb.points[k], cb.points[k + 1], ca.points[i], ca.points[i + 1])
                                local sa = cumA[i] + (cumA[i + 1] - cumA[i]) * t
                                local sb = cumB[k] + (cumB[k + 1] - cumB[k]) * u
                                ca.cuts[#ca.cuts + 1] = { sa - half, sa + half }
                                cb.cuts[#cb.cuts + 1] = { sb - half, sb + half }
                                local p = ca.points[i] + (ca.points[i + 1] - ca.points[i]) * t
                                local d = normalized(flat(ca.points[i + 1] - ca.points[i])) * half
                                local duplicate = false
                                for _, q in ipairs(centres) do
                                    if flat(q - p):magnitude() < 0.1 then duplicate = true end
                                end
                                if not duplicate then
                                    centres[#centres + 1] = p
                                    squares[#squares + 1] = stripPairs({ p - d, p + d }, width)
                                end
                            end
                        end
                    end
                end
            end
        end
    end

    local strips = {}
    for _, c in ipairs(curves) do
        table.sort(c.cuts, function(x, y) return x[1] < y[1] end)
        for _, piece in ipairs(without(c.points, c.cuts)) do strips[#strips + 1] = stripPairs(piece, width) end
    end
    return result({
        { parameters = ctx.parameters, parameter = "cableCarRailTexture", fallback = RAIL_TEXTURE, width = width, strips = strips },
        { parameters = ctx.parameters, parameter = "cableCarCrossingTexture", fallback = CROSSING_TEXTURE, width = width, strips = squares }
    })
end

-- Availability of the parameters in the panels (enabledWhen, given snapshots of the element and its neighbors)

local function cableRoads(ctx)
    local count, seen = 0, {}
    for _, n in ipairs(ctx.neighbors) do
        if n.kind == "road" and n.state.cableCarLine and not seen[n.id] then
            seen[n.id] = true
            count = count + 1
        end
    end
    return count
end

function M.roadAvailable(_, ctx)
    return ctx.element.state.cableCarLine == true
end

function M.roadOptionsAvailable(_, ctx)
    return ctx.element.state.cableCarLine == true and ctx.element.state.cableCarRails == true
end

function M.intersectionAvailable(_, ctx)
    return goesOn(cableRoads(ctx))
end

function M.intersectionOptionsAvailable(_, ctx)
    return goesOn(cableRoads(ctx)) and ctx.element.state.cableCarRails == true
end

function M.crossingOptionsAvailable(_, ctx)
    return goesOn(cableRoads(ctx)) and ctx.element.state.cableCarRails == true and ctx.element.state.cableCarHideCrossings ~= true
end

return M
