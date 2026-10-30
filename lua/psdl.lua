-- The custom elements of the PSDL (the room attributes, see elements/customElements): the geometry shown in the editor,
-- close to what MM2 draws from each attribute, and the constraints keeping their points where the attribute needs them.
-- The heights of the PSDL (facades, roofs...) come from the points, they are computed by the exporter.

local M = {}

local CURB = 0.15 -- the road surface is this much below the sidewalks
local UV_SCALE = -0.25 -- as the terrain patches (uMult, vMult)
local UP = vec3(0, 1, 0)

-- Meshes

local function newMesh(texture)
    return { texture = texture, vertices = {}, uvs = {}, triangles = {} }
end

local function addVertex(mesh, p, uv)
    mesh.vertices[#mesh.vertices + 1] = p
    mesh.uvs[#mesh.uvs + 1] = uv or vec2(0, 0)
    return #mesh.vertices - 1
end

-- a triangle seen from above (its winding is chosen so that it faces up)
local function upTriangle(mesh, a, b, c)
    local va, vb, vc = mesh.vertices[a + 1], mesh.vertices[b + 1], mesh.vertices[c + 1]
    local n = (vb - va):cross(vc - va)
    local t = mesh.triangles
    if n.y >= 0 then
        t[#t + 1] = a; t[#t + 1] = b; t[#t + 1] = c
    else
        t[#t + 1] = a; t[#t + 1] = c; t[#t + 1] = b
    end
end

local function bothTriangles(mesh, a, b, c)
    local t = mesh.triangles
    t[#t + 1] = a; t[#t + 1] = b; t[#t + 1] = c
    t[#t + 1] = a; t[#t + 1] = c; t[#t + 1] = b
end

-- a quad from a, b, c, d in order around it, facing up
local function upQuad(mesh, pa, pb, pc, pd, ua, ub, uc, ud)
    local a = addVertex(mesh, pa, ua)
    local b = addVertex(mesh, pb, ub)
    local c = addVertex(mesh, pc, uc)
    local d = addVertex(mesh, pd, ud)
    upTriangle(mesh, a, b, c)
    upTriangle(mesh, a, c, d)
end

-- a quad visible from both sides (walls, facades): each side has its own vertices, so that their normals don't cancel
local function wallQuad(mesh, pa, pb, pc, pd, ua, ub, uc, ud)
    local t = mesh.triangles
    for side = 1, 2 do
        local a = addVertex(mesh, pa, ua)
        local b = addVertex(mesh, pb, ub)
        local c = addVertex(mesh, pc, uc)
        local d = addVertex(mesh, pd, ud)
        if side == 1 then
            t[#t + 1] = a; t[#t + 1] = b; t[#t + 1] = c
            t[#t + 1] = a; t[#t + 1] = c; t[#t + 1] = d
        else
            t[#t + 1] = a; t[#t + 1] = c; t[#t + 1] = b
            t[#t + 1] = a; t[#t + 1] = d; t[#t + 1] = c
        end
    end
end

local function horizontalDistance(a, b)
    return vec2(a.x - b.x, a.z - b.z):magnitude()
end

-- the uv of a surface textured from above: the world position, as the terrain patches
local function groundUV(p)
    return vec2(p.x * UV_SCALE, p.z * UV_SCALE)
end

-- the length along a polyline at each point
local function lengths(points)
    local res = { 0 }
    for i = 2, #points do
        res[i] = res[i - 1] + points[i]:distance(points[i - 1])
    end
    return res
end

-- a strip between two polylines (same count), facing up: u from u0 to u1 along it every vScale meters, v from 0 to
-- 1 across it (from left to right)
local function strip(mesh, left, right, v0, v1, uScale)
    local l = lengths(left)
    for i = 1, #left - 1 do
        upQuad(mesh, left[i], left[i + 1], right[i + 1], right[i],
            vec2(l[i] / uScale, v0), vec2(l[i + 1] / uScale, v0), vec2(l[i + 1] / uScale, v1), vec2(l[i] / uScale, v1))
    end
end

-- a vertical strip from a polyline up by height (both sides visible)
local function verticalStrip(mesh, line, bottom, height, vScale)
    local l = lengths(line)
    for i = 1, #line - 1 do
        local a, b = line[i] + UP * bottom, line[i + 1] + UP * bottom
        wallQuad(mesh, a, b, b + UP * height, a + UP * height,
            vec2(l[i] / vScale, 0), vec2(l[i + 1] / vScale, 0), vec2(l[i + 1] / vScale, 1), vec2(l[i] / vScale, 1))
    end
end

local function column(sections, name)
    local res = {}
    for i, s in ipairs(sections) do res[i] = s[name] end
    return res
end

local function raised(points, height)
    local res = {}
    for i, p in ipairs(points) do res[i] = p + UP * height end
    return res
end

local function midpoints(a, b)
    local res = {}
    for i = 1, #a do res[i] = a[i]:lerp(b[i], 0.5) end
    return res
end

local function width(a, b)
    return math.max(horizontalDistance(a[1], b[1]), 0.1)
end

-- a sidewalk of a road: its top from the outer edge to the curb (CURB above the road edge), and the curb (the
-- texture repeats twice every sidewalk width along it, as the procedural roads)
local function sidewalk(sidewalkMesh, outer, roadEdge)
    local curbTop = raised(roadEdge, CURB)
    strip(sidewalkMesh, outer, curbTop, 0, 1, width(outer, roadEdge) * 0.5)
    verticalStrip(sidewalkMesh, roadEdge, 0, CURB, 1)
end

-- the lines of the props of the sidewalks (props containers "right" and "left"), as the procedural psdl roads: from the
-- top of the curb to the outer edge
local function sidewalkPropLines(sections)
    local res = {}
    for _, side in ipairs({ "right", "left" }) do
        res[#res + 1] = {
            container = side,
            startBound = raised(column(sections, side .. "Road"), CURB),
            endBound = column(sections, side .. "Sidewalk")
        }
    end
    return res
end

-- Roads

-- the road surface between the two edges, its texture mirrored on the center line (repeating twice every half
-- width along it, as the procedural roads)
local function roadSurface(mesh, left, right)
    local center = midpoints(left, right)
    local uScale = width(left, right) * 0.25
    strip(mesh, left, center, 0, 1, uScale)
    strip(mesh, center, right, 1, 0, uScale)
end

-- Road with sidewalks (0x00): sections of left sidewalk, left road edge, right road edge, right sidewalk
function M.roadWithSidewalks(v, ctx)
    local s = ctx.points.sections
    local road = newMesh("texture")
    local sidewalks = newMesh("sidewalkTexture")
    local leftRoad, rightRoad = column(s, "leftRoad"), column(s, "rightRoad")
    roadSurface(road, leftRoad, rightRoad)
    sidewalk(sidewalks, column(s, "leftSidewalk"), leftRoad)
    sidewalk(sidewalks, column(s, "rightSidewalk"), rightRoad)
    return {
        meshes = { road, sidewalks },
        lines = M.sectionLines(s, { "leftSidewalk", "leftRoad", "rightRoad", "rightSidewalk" }),
        propLines = sidewalkPropLines(s)
    }
end

-- Road without sidewalks (0x02, or 0x00 without sidewalks): sections of left and right edge
function M.roadWithoutSidewalks(v, ctx)
    local s = ctx.points.sections
    local road = newMesh("texture")
    local left, right = column(s, "left"), column(s, "right")
    if v.style == 1 then
        roadSurface(road, left, right)
    else
        strip(road, left, right, 0, 1, width(left, right) * 0.5)
    end
    return { meshes = { road }, lines = M.sectionLines(s, { "left", "right" }) }
end

-- the length along a polyline at each point, scaled so that the whole length is a whole number of meters (the u of the
-- procedural dividers: about one repeat per meter)
local function wholeLengths(points)
    local l = lengths(points)
    local total = l[#l]
    local k = total > 1e-6 and math.max(1, math.floor(total + 0.5)) / total or 1
    for i = 1, #l do l[i] = l[i] * k end
    return l
end

-- a strip between two polylines (same count), u given per point, v from va (on a) to vb (on b); walls are visible from
-- both sides, the other strips face up
local function sweep(mesh, a, b, u, va, vb, wall)
    local quad = wall and wallQuad or upQuad
    for i = 1, #a - 1 do
        quad(mesh, a[i], a[i + 1], b[i + 1], b[i], vec2(u[i], va), vec2(u[i + 1], va), vec2(u[i + 1], vb), vec2(u[i], vb))
    end
end

-- the divider of a divided road (as the procedural psdl roads and the game draw it) between the left and right divider
-- edges: flat (a strip at road level, value: the repeats of the texture across it), elevated (value: its height, the
-- top edges beveled by as much) or wedged (1 m high, the top 0.5 m narrower on each side); closed ends get a cap
local function divider(meshes, v, left, right)
    local u = wholeLengths(left)
    if v.dividerType == 1 then
        sweep(meshes.flat, left, right, u, 0, v.dividerValue or 0, false)
        return
    end
    local elevated = v.dividerType == 2
    local rise = elevated and (v.dividerValue or 0) or 1
    local inset = elevated and rise or 0.5
    -- the corners of the cross section: p1, p4 above the edges, p2, p3 the top edges moved inward by the inset
    local p1, p2, p3, p4 = {}, {}, {}, {}
    for i = 1, #left do
        local across = vec3(right[i].x - left[i].x, 0, right[i].z - left[i].z)
        local inward = across:magnitude() > 1e-6 and across:normalize() * inset or vec3(0, 0, 0)
        p1[i] = left[i] + UP * rise
        p4[i] = right[i] + UP * rise
        p2[i] = p1[i] + inward
        p3[i] = p4[i] - inward
    end
    -- the outer corners of the caps: the top edges for the elevated divider, the top of the wedge otherwise
    local capLeft, capRight = p1, p4
    if elevated then
        sweep(meshes.side, left, p1, u, 1, 0, true)
        sweep(meshes.side, right, p4, u, 1, 0, true)
        sweep(meshes.flat, p1, p2, u, 1, 0, false)
        sweep(meshes.flat, p4, p3, u, 1, 0, false)
    else
        sweep(meshes.flat, left, p2, u, 1, 0, false)
        sweep(meshes.flat, right, p3, u, 1, 0, false)
        capLeft, capRight = p2, p3
    end
    sweep(meshes.top, p2, p3, u, 1, 0, false)
    local n = #left
    if v.closeStart then
        wallQuad(meshes.cap, left[1], capLeft[1], capRight[1], right[1], vec2(0, 1), vec2(0, 0), vec2(1, 0), vec2(1, 1))
    end
    if v.closeEnd then
        wallQuad(meshes.cap, left[n], capLeft[n], capRight[n], right[n], vec2(0, 1), vec2(0, 0), vec2(1, 0), vec2(1, 1))
    end
end

-- Divided road (0x08): sections of left sidewalk, left road edge, left divider, right divider, right road edge, right sidewalk
function M.dividedRoad(v, ctx)
    local s = ctx.points.sections
    local road = newMesh("texture")
    local sidewalks = newMesh("sidewalkTexture")
    local dividerMeshes = {
        side = newMesh("dividerSideTexture"),
        flat = newMesh("dividerFlatTexture"),
        top = newMesh("dividerTopTexture"),
        cap = newMesh("dividerCapTexture")
    }
    local leftRoad, rightRoad = column(s, "leftRoad"), column(s, "rightRoad")
    local leftDivider, rightDivider = column(s, "leftDivider"), column(s, "rightDivider")
    -- the road surface on each side of the divider, from the curb to the divider: half of the texture mirrored on the
    -- center line each (as the procedural roads, repeating twice every half width of the whole road along it)
    local uScale = width(leftRoad, rightRoad) * 0.25
    strip(road, leftRoad, leftDivider, 0, 1, uScale)
    strip(road, rightDivider, rightRoad, 1, 0, uScale)
    if not v.noSidewalks then
        sidewalk(sidewalks, column(s, "leftSidewalk"), leftRoad)
        sidewalk(sidewalks, column(s, "rightSidewalk"), rightRoad)
    end
    -- 0 invisible, 1 flat, 2 elevated, 3 wedged
    if (v.dividerType or 0) > 0 then divider(dividerMeshes, v, leftDivider, rightDivider) end
    local names = { "leftSidewalk", "leftRoad", "leftDivider", "rightDivider", "rightRoad", "rightSidewalk" }
    if v.noSidewalks then names = { "leftRoad", "leftDivider", "rightDivider", "rightRoad" } end
    local propLines = v.noSidewalks and {} or sidewalkPropLines(s)
    -- the props on the divider (container "middle"), on its top as the procedural psdl roads (flat and elevated only)
    if v.dividerType == 1 or v.dividerType == 2 then
        local height = v.dividerType == 2 and (v.dividerValue or 0) or 0
        propLines[#propLines + 1] = { container = "middle", startBound = raised(leftDivider, height), endBound = raised(rightDivider, height) }
    end
    return {
        meshes = { road, sidewalks, dividerMeshes.side, dividerMeshes.flat, dividerMeshes.top, dividerMeshes.cap },
        lines = M.sectionLines(s, names),
        propLines = propLines
    }
end

-- the edges of a road and its sections, shown while it is edited
function M.sectionLines(sections, names)
    local lines = {}
    for _, name in ipairs(names) do
        lines[#lines + 1] = { points = column(sections, name), color = "cyan", heightOffset = 0.05 }
    end
    for _, section in ipairs(sections) do
        local points = {}
        for _, name in ipairs(names) do points[#points + 1] = section[name] end
        lines[#lines + 1] = { points = points, color = "white", heightOffset = 0.05 }
    end
    return lines
end

-- Rooms

-- the triangles of a simple polygon seen from above (ear clipping), as triples of indices from 1; what is left of a
-- polygon that isn't simple is not covered
local function polygonTriangles(points)
    local n = #points
    local res = {}
    if n < 3 then return res end
    local function cross(o, a, b) return (a.x - o.x) * (b.z - o.z) - (a.z - o.z) * (b.x - o.x) end
    local area = 0
    for i = 1, n do
        local a, b = points[i], points[i % n + 1]
        area = area + a.x * b.z - b.x * a.z
    end
    local sign = area >= 0 and 1 or -1
    local left = {}
    for i = 1, n do left[i] = i end
    while #left > 3 do
        local m = #left
        local clipped = false
        for k = 1, m do
            local ia, ib, ic = left[(k - 2) % m + 1], left[k], left[k % m + 1]
            local a, b, c = points[ia], points[ib], points[ic]
            if cross(a, b, c) * sign > 0 then
                local ear = true
                for _, j in ipairs(left) do
                    local p = points[j]
                    if j ~= ia and j ~= ib and j ~= ic and cross(a, b, p) * sign >= 0 and cross(b, c, p) * sign >= 0 and cross(c, a, p) * sign >= 0 then
                        ear = false
                        break
                    end
                end
                if ear then
                    res[#res + 1] = { ia, ib, ic }
                    table.remove(left, k)
                    clipped = true
                    break
                end
            end
        end
        if not clipped then return res end
    end
    res[#res + 1] = { left[1], left[2], left[3] }
    return res
end

-- a room: its perimeter (when set manually; otherwise the exporter computes it from the attributes), a closed line
-- always shown (unless the room outlines are turned off in the View menu), so that the room can be clicked, and a
-- transparent surface inside it while its attributes draw nothing (e.g. only BAI roads), to click it more easily
function M.room(v, ctx)
    local perimeter = ctx.points.perimeter or {}
    if #perimeter < 2 then return { meshes = {}, lines = {} } end
    local fill = newMesh("_TRANSPARENT_")
    fill.placeholder = true
    for _, p in ipairs(perimeter) do addVertex(fill, p + UP * 0.05, groundUV(p)) end
    for _, t in ipairs(polygonTriangles(perimeter)) do upTriangle(fill, t[1] - 1, t[2] - 1, t[3] - 1) end
    return {
        meshes = { fill },
        lines = { { points = perimeter, closed = true, always = true, toggle = "roomOutlines", color = "magenta", heightOffset = 0.1 } }
    }
end

-- Tunnels and railings

-- the edges of the road a road tunnel applies to (the outer edges of its sidewalks, if it has them)
local function roadEdges(road)
    if road == nil then return nil, nil end
    local s = road.points.sections
    if s == nil or #s < 2 then return nil, nil end
    if road.typeName == "roadWithoutSidewalks" then return column(s, "left"), column(s, "right") end
    return column(s, "leftSidewalk"), column(s, "rightSidewalk")
end

local function tunnelWalls(v, walls, ceilingFrom, ceilingTo)
    local res = { meshes = {}, lines = {} }
    local leftWall = newMesh("texture0")
    local rightWall = newMesh("texture1")
    local ceiling = newMesh("texture2")
    local h = math.max(v.height, 0.1)
    if v.leftSide and walls.left then verticalStrip(leftWall, walls.left, 0, h, h) end
    if v.rightSide and walls.right then verticalStrip(rightWall, walls.right, 0, h, h) end
    if (v.flatCeiling or v.curvedCeiling) and ceilingFrom and ceilingTo then
        strip(ceiling, raised(ceilingFrom, h), raised(ceilingTo, h), 0, 1, h)
    end
    res.meshes = { leftWall, rightWall, ceiling }
    return res
end

-- Road tunnel/railing (0x09, subtype 3): walls along the road it applies to (the road parameter)
function M.roadTunnel(v, ctx)
    local left, right = roadEdges(ctx.references.road)
    if left == nil then return {} end
    local res = tunnelWalls(v, { left = left, right = right }, left, right)
    res.lines = {
        { points = left, color = "orange", heightOffset = 0.1 },
        { points = right, color = "orange", heightOffset = 0.1 }
    }
    return res
end

-- Junction tunnel/railing (0x09, subtype 0): walls along the edges of the perimeter of the room between consecutive
-- points of each wall
function M.junctionTunnel(v, ctx)
    local mesh = newMesh("texture0")
    local h = math.max(v.height, 0.1)
    local lines = {}
    for _, wall in ipairs(ctx.points.walls) do
        verticalStrip(mesh, wall.points, 0, h, h)
        lines[#lines + 1] = { points = wall.points, color = "orange", heightOffset = 0.1 }
    end
    return { meshes = { mesh }, lines = lines }
end

-- Intersections

-- Sidewalk strip (0x01): sections of inner (at the road level) and outer vertex, the curb raised CURB above the inner
-- one. Unlike the sidewalks of the roads, it is textured from above (as the procedural intersections and the game),
-- the curb takes the uv of its top at both ends (the texture is stretched on it)
function M.sidewalkStrip(v, ctx)
    local s = ctx.points.sections
    local mesh = newMesh("texture")
    local inner, outer = column(s, "inner"), column(s, "outer")
    local curbTop = raised(inner, CURB)
    for i = 1, #s - 1 do
        local a, b = groundUV(inner[i]), groundUV(inner[i + 1])
        upQuad(mesh, curbTop[i], curbTop[i + 1], outer[i + 1], outer[i], a, b, groundUV(outer[i + 1]), groundUV(outer[i]))
        wallQuad(mesh, inner[i], inner[i + 1], curbTop[i + 1], curbTop[i], a, b, b, a)
    end
    local lines = {
        { points = inner, color = "cyan", heightOffset = 0.05 },
        { points = outer, color = "cyan", heightOffset = 0.05 }
    }
    return { meshes = { mesh }, lines = lines }
end

-- Sidewalk end piece (0x01 with the first two vertices 0 or 1): a triangle from a to b, raised CURB above a
function M.sidewalkCap(v, ctx)
    local p = ctx.points
    local mesh = newMesh("texture")
    local a = addVertex(mesh, p.a, vec2(0, 0))
    local b = addVertex(mesh, p.b, vec2(1, 0))
    local c = addVertex(mesh, p.a + UP * CURB, vec2(0, 1))
    bothTriangles(mesh, a, b, c)
    return { meshes = { mesh }, lines = { { points = { p.a, p.b }, color = "cyan", heightOffset = 0.05 } } }
end

-- Crosswalk rectangle (0x04): a strip of two pairs of corners, as the game draws it (p1 p2 one end of the crosswalk,
-- p3 p4 the other, so not in order around it), textured as the procedural crosswalks: once from p1 to p2, along it
-- a whole number of times keeping the texture about square
function M.crosswalk(v, ctx)
    local p = ctx.points
    local mesh = newMesh("texture")
    local raise = UP * 0.02
    local reps = math.max(1, math.floor(horizontalDistance(p.p1, p.p3) / math.max(horizontalDistance(p.p1, p.p2), 0.1) + 0.5))
    local a = addVertex(mesh, p.p1 + raise, vec2(0, reps))
    local b = addVertex(mesh, p.p2 + raise, vec2(1, reps))
    local c = addVertex(mesh, p.p3 + raise, vec2(0, 0))
    local d = addVertex(mesh, p.p4 + raise, vec2(1, 0))
    upTriangle(mesh, a, b, c)
    upTriangle(mesh, b, d, c)
    return { meshes = { mesh }, lines = { { points = { p.p1, p.p2, p.p4, p.p3 }, closed = true, color = "cyan", heightOffset = 0.05 } } }
end

-- Triangle fans

-- the outline of a mesh (its edges used by one triangle only)
local function outline(ctx)
    local count = {}
    local t = ctx.triangles
    local function key(a, b)
        if a < b then return a .. ":" .. b end
        return b .. ":" .. a
    end
    for i = 1, #t, 3 do
        for j = 0, 2 do
            local a, b = t[i + j], t[i + (j + 1) % 3]
            local k = key(a, b)
            count[k] = (count[k] or 0) + 1
        end
    end
    local lines = {}
    for i = 1, #t, 3 do
        for j = 0, 2 do
            local a, b = t[i + j], t[i + (j + 1) % 3]
            if count[key(a, b)] == 1 then
                lines[#lines + 1] = { points = { ctx.vertices[a + 1], ctx.vertices[b + 1] }, color = "yellow", heightOffset = 0.05 }
            end
        end
    end
    return lines
end

-- the mesh of the element as it is, textured from above (uvs: the world position, as the terrain patches)
local function fanMesh(ctx, texture, offset)
    local mesh = newMesh(texture)
    local uvs = {}
    for i, p in ipairs(ctx.vertices) do
        uvs[i] = groundUV(p)
        addVertex(mesh, p + UP * (offset or 0), uvs[i])
    end
    local t = ctx.triangles
    for i = 1, #t, 3 do upTriangle(mesh, t[i], t[i + 1], t[i + 2]) end
    return mesh, uvs
end

-- Triangle fan (0x06), road triangle fan (0x05), roof triangle fan (0x0c): the whole mesh, split in fans by the exporter
function M.fan(v, ctx)
    local mesh, uvs = fanMesh(ctx, "texture")
    return { meshes = { mesh }, lines = outline(ctx), uvs = uvs }
end

-- the vertices of a road triangle fan or of a roof are all at the height of the vertex moved last
function M.flatMesh(v, ctx)
    local moved = nil
    for i = 1, #ctx.vertices do
        if ctx.moved.vertices[i] then moved = i break end
    end
    if moved == nil then return {} end
    local y = ctx.vertices[moved].y
    local res = {}
    for i, p in ipairs(ctx.vertices) do
        if math.abs(p.y - y) > 1e-4 then res[i] = vec3(p.x, y, p.z) end
    end
    return { vertices = res }
end

-- Buildings

-- Facade (0x0b): a vertical rectangle repeating its texture uRepeat by vRepeat times (v = 0 is the top of the texture,
-- as in the procedural facades)
function M.facade(v, ctx)
    local p = ctx.points
    local mesh = newMesh("texture")
    local u, w = math.max(v.uRepeat, 1), math.max(v.vRepeat, 1)
    wallQuad(mesh, p.bottomLeft, p.bottomRight, p.topRight, p.topLeft, vec2(0, w), vec2(u, w), vec2(u, 0), vec2(0, 0))
    return { meshes = { mesh }, lines = { { points = { p.bottomLeft, p.bottomRight, p.topRight, p.topLeft }, closed = true, color = "cyan" } } }
end

-- Facade bound (0x07): the collision of the facades, not drawn (it is where its facades are), its outline shown while
-- it is edited
function M.facadeBound(v, ctx)
    local p = ctx.points
    local mesh = newMesh(nil)
    mesh.pickOnly = true
    wallQuad(mesh, p.bottomLeft, p.bottomRight, p.topRight, p.topLeft)
    return { meshes = { mesh }, lines = { { points = { p.bottomLeft, p.bottomRight, p.topRight, p.topLeft }, closed = true, color = "magenta" } } }
end

-- Sliver (0x03): the bottom of a facade following the ground (its bottom edge can be slanted), texture scaled by
-- textureScale (a value of the height list of the PSDL)
function M.sliver(v, ctx)
    local p = ctx.points
    local mesh = newMesh("texture")
    local scale = v.textureScale > 0 and v.textureScale or 1
    local len = horizontalDistance(p.bottomLeft, p.bottomRight)
    local top = p.topLeft.y
    local u = math.max(1, math.floor(len * scale + 0.5))
    wallQuad(mesh, p.bottomLeft, p.bottomRight, p.topRight, p.topLeft,
        vec2(0, (top - p.bottomLeft.y) * scale), vec2(u, (top - p.bottomRight.y) * scale), vec2(u, 0), vec2(0, 0))
    return { meshes = { mesh }, lines = { { points = { p.bottomLeft, p.bottomRight, p.topRight, p.topLeft }, closed = true, color = "cyan" } } }
end

-- the four corners of a facade, facade bound or sliver: the top corners are above the bottom ones, the top edge is
-- horizontal (and the bottom one too for the facades)
local function verticalRectangle(ctx, flatBottom)
    local p, m = ctx.points, ctx.moved.points
    local cur = { bottomLeft = p.bottomLeft, bottomRight = p.bottomRight, topLeft = p.topLeft, topRight = p.topRight }
    for _, side in ipairs({ "Left", "Right" }) do
        local b, t = "bottom" .. side, "top" .. side
        if m[t] then
            cur[b] = vec3(cur[t].x, cur[b].y, cur[t].z)
        elseif m[b] then
            cur[t] = vec3(cur[b].x, cur[t].y, cur[b].z)
        end
    end
    local function row(l, r)
        if m[r] and not m[l] then
            cur[l] = vec3(cur[l].x, cur[r].y, cur[l].z)
        else
            cur[r] = vec3(cur[r].x, cur[l].y, cur[r].z)
        end
    end
    row("topLeft", "topRight")
    if flatBottom then row("bottomLeft", "bottomRight") end
    local res = {}
    for name, value in pairs(cur) do
        if value:distance(p[name]) > 1e-4 then res[name] = value end
    end
    return { points = res }
end

function M.facadeConstraints(v, ctx)
    return verticalRectangle(ctx, true)
end

function M.slantedConstraints(v, ctx)
    return verticalRectangle(ctx, false)
end

-- Group of building parts: they go in the room found at location (or at frontLocation if there is none, as the
-- procedural buildings facing a road with nothing behind them)
function M.buildingGroup(v, ctx)
    local function cross(c, d, color)
        return {
            { points = { c + vec3(-d, 0, 0), c + vec3(d, 0, 0) }, color = color, heightOffset = 0.2, width = 0.3 },
            { points = { c + vec3(0, 0, -d), c + vec3(0, 0, d) }, color = color, heightOffset = 0.2, width = 0.3 }
        }
    end
    local lines = cross(ctx.points.location, 1.5, "cyan")
    for _, l in ipairs(cross(ctx.points.frontLocation, 0.75, "blue")) do lines[#lines + 1] = l end
    lines[#lines + 1] = { points = { ctx.points.location, ctx.points.frontLocation }, color = "blue", heightOffset = 0.2 }
    return { lines = lines }
end

-- Traffic (BAI)

-- Lane colours of the procedural roads (trafficTypes in elements/roads/psdl/settings.json)
local PEDESTRIAN_COLOR = vec3(224 / 255, 32 / 255, 224 / 255)
local FORWARD_COLOR = vec3(0, 128 / 255, 1)
local BACKWARD_COLOR = vec3(224 / 255, 32 / 255, 0)

-- BAI road: sections of right edge, right curb, the backward lanes (right to left), the forward lanes, left curb, left edge
-- (the right side is the left one of the road it was converted from)
function M.baiRoad(v, ctx)
    local s = ctx.points.sections
    local lines = {
        { points = column(s, "rightEdge"), color = "white", heightOffset = 0.15 },
        { points = column(s, "rightCurb"), color = "white", heightOffset = 0.15 },
        { points = column(s, "leftCurb"), color = "white", heightOffset = 0.15 },
        { points = column(s, "leftEdge"), color = "white", heightOffset = 0.15 }
    }
    -- thin lines slightly above the points, as the lanes of the procedural roads (shown also while anything in the room
    -- is edited, and with the lanes of the roads by View > Show all traffic lanes)
    local function lane(points, color)
        lines[#lines + 1] = { points = points, color = color, heightOffset = 0.01, always = v.alwaysShown, withContainer = true, traffic = true }
    end
    local function lanes(name, color)
        local n = #s[1][name]
        for k = 1, n do
            local points = {}
            for i, section in ipairs(s) do points[i] = section[name][k] end
            lane(points, color)
        end
    end
    -- the pedestrians walk in the middle of the sidewalk (at the height of its edge)
    local function sidewalk(edge, curb)
        local points = {}
        for i, section in ipairs(s) do
            local e, c = section[edge], section[curb]
            points[i] = vec3((e.x + c.x) * 0.5, e.y, (e.z + c.z) * 0.5)
        end
        lane(points, PEDESTRIAN_COLOR)
    end
    if v.geoSidewalks then
        if not v.noLeftPedestrians then sidewalk("rightEdge", "rightCurb") end
        if not v.noRightPedestrians then sidewalk("leftEdge", "leftCurb") end
    end
    -- in alleys (pedestrian streets) the lanes are walked by pedestrians
    lanes("backwardLanes", v.alley and PEDESTRIAN_COLOR or BACKWARD_COLOR)
    lanes("forwardLanes", v.alley and PEDESTRIAN_COLOR or FORWARD_COLOR)
    return { lines = lines }
end

-- the points of a BAI road computed from the road attributes converted from the same road (its siblings, see
-- derivedPoints in settings.json), as the procedural export does without the lanes drawn in the editor
-- (json_processor.get_bai_cross_sections): the lanes (as many as now) spread evenly between each curb and the middle of
-- the road (the divider if divided, the other curb if a direction has no lanes). nil if there are no road attributes
local function sameSection(a, b)
    return a.re:distance(b.re) < 1e-3 and a.le:distance(b.le) < 1e-3
end

local function reversedPart(part)
    local res = {}
    for i = #part, 1, -1 do
        local s = part[i]
        res[#res + 1] = { re = s.le, rc = s.lc, rd = s.ld, ld = s.rd, lc = s.rc, le = s.re }
    end
    return res
end

function M.baiRoadPoints(v, ctx)
    -- the sections of each road attribute with the BAI names (its first point is the right edge of the BAI)
    local parts = {}
    for _, sibling in ipairs(ctx.siblings) do
        local part = {}
        for i, s in ipairs(sibling.points.sections or {}) do
            if sibling.typeName == "roadWithSidewalks" then
                part[i] = { re = s.leftSidewalk, rc = s.leftRoad, lc = s.rightRoad, le = s.rightSidewalk }
            elseif sibling.typeName == "roadWithoutSidewalks" then
                part[i] = { re = s.left, rc = s.left, lc = s.right, le = s.right }
            elseif sibling.typeName == "dividedRoad" then
                part[i] = { re = s.leftSidewalk, rc = s.leftRoad, rd = s.leftDivider, ld = s.rightDivider, lc = s.rightRoad, le = s.rightSidewalk }
            end
        end
        if #part >= 2 then parts[#parts + 1] = part end
    end
    if #parts == 0 then return nil end
    -- chained where their end sections are the same (a road in more rooms), each joint once
    local chain = parts[1]
    table.remove(parts, 1)
    local found = true
    while found and #parts > 0 do
        found = false
        for k, part in ipairs(parts) do
            for _, p in ipairs({ part, reversedPart(part) }) do
                if sameSection(chain[#chain], p[1]) then
                    for i = 2, #p do chain[#chain + 1] = p[i] end
                    found = true
                elseif sameSection(p[#p], chain[1]) then
                    for i = 2, #chain do p[#p + 1] = chain[i] end
                    chain = p
                    found = true
                end
                if found then break end
            end
            if found then
                table.remove(parts, k)
                break
            end
        end
    end
    -- in the direction of the BAI road now
    local first = ctx.points.sections[1].rightEdge
    if first:distance(chain[#chain].le) < first:distance(chain[1].re) then chain = reversedPart(chain) end
    local f = #ctx.points.sections[1].forwardLanes
    local b = #ctx.points.sections[1].backwardLanes
    local sections = {}
    for i, s in ipairs(chain) do
        local rInner, lInner = s.rd, s.ld
        -- not "== nil": Lua-CSharp calls the __eq of the vectors with nil, which fails
        if not rInner then
            local mid = s.rc:lerp(s.lc, 0.5)
            rInner = f > 0 and mid or s.lc
            lInner = b > 0 and mid or s.rc
        end
        local backward, forward = {}, {}
        for k = 1, b do backward[k] = s.rc + (rInner - s.rc) * ((k - 0.5) / b) end
        for k = 1, f do forward[k] = lInner + (s.lc - lInner) * ((k - 0.5) / f) end
        sections[i] = { rightEdge = s.re, rightCurb = s.rc, backwardLanes = backward, forwardLanes = forward, leftCurb = s.lc, leftEdge = s.le }
    end
    return { points = { sections = sections } }
end

-- BAI intersection: its center
function M.baiIntersection(v, ctx)
    local c = ctx.points.center
    local d = 1.5
    return { lines = {
        { points = { c + vec3(-d, 0, -d), c + vec3(d, 0, -d), c + vec3(d, 0, d), c + vec3(-d, 0, d) }, closed = true, color = "magenta", heightOffset = 0.2, width = 0.3, always = v.alwaysShown, withContainer = true, traffic = true },
    } }
end

-- A null PSDL texture reference disables drawing and collision, while the editor can still pick the shape.
for _, name in ipairs({"crosswalk", "dividedRoad", "facade", "facadeBound", "fan", "junctionTunnel", "roadTunnel", "roadWithSidewalks", "roadWithoutSidewalks", "sidewalkCap", "sidewalkStrip", "sliver"}) do
    local build = M[name]
    M[name] = function(v, ctx)
        local result = build(v, ctx)
        if v.invisible then
            for _, mesh in ipairs(result.meshes or {}) do mesh.pickOnly = true end
        end
        return result
    end
end

return M
