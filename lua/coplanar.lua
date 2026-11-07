-- "Make coplanar" (the makeCoplanar parameter of the psdl roads): the post-process pass of the road types (postProcess in
-- their settings.json). The colliders of the MM2 roads are quads, so the four corners of each section quad must be on one
-- plane, or the mesh and the collider differ. A road bending both left-right and up-down (e.g. a curved slope) has twisted
-- quads: this rotates each section around its center so that its quad with the previous section is flat, where possible.
-- It doesn't always work: on a tight curve the result can look bad.
--
-- A port of the code of the builder that did this, kept identical to give the same roads, quirks included:
-- * the neighbours are the sections as computed, not the ones already rotated;
-- * the points of the neighbours are rebuilt with the offsets of the section being rotated (they differ only with
--   variable sections, e.g. the width fix of the low-poly roads);
-- * the first section, and the last one if it is on an intersection, are never rotated;
-- * a rolled road is left as it is (a twisted road has no flat quads).

local M = {}

local worldRight = vec3(1, 0, 0)
local worldBack = vec3(0, 0, -1)

-- the plane through a, b and c, as the builder's GameEngine.Plane.Create: normal (b - a) x (c - a), normalized
local function plane(a, b, c)
    local normal = (a - b):cross(a - c):normalize()
    return { normal = normal, d = normal:dot(a) }
end

local function distance(p, point)
    return p.normal:dot(point) - p.d
end

-- the vertex j of a section, rebuilt with other offsets (see above)
local function vertex(section, offsets, j)
    return section.point + section.right * offsets[j]
end

function M.postProcess(v, ctx)
    if not v.makeCoplanar or ctx.rolled then return nil end
    local sections = ctx.sections
    local n = #sections
    local tolerance = v.pointPlaneTreshold
    if tolerance <= 0 then tolerance = 0.02 end -- the default of the builder (presets without the value)
    local result = {}
    for i = 2, n do
        if not (i == n and v.hasEndIntersection) then
            local cur = sections[i]
            local offsets = cur.offsets
            local count = #offsets
            if count > 0 then
                local mid = math.floor(count / 2) + 1
                local vL, vM, vR = cur.vertices[1], cur.vertices[mid], cur.vertices[count]
                local prev = sections[i - 1]
                local p1 = plane(vertex(prev, offsets, 1), vM, vertex(prev, offsets, count))
                local p2
                if i < n then
                    p2 = plane(vL, vertex(sections[i + 1], offsets, mid), vR)
                else
                    p2 = plane(vM + worldRight, vM, vM + worldBack)
                end
                local across = vR - vL
                local dir = p1.normal:cross(p2.normal):normalize()
                if dir:dot(across) < 0 then dir = -dir end
                dir = dir / math.cos(math.rad(dir:angle(across)))
                if math.abs(distance(p1, vL)) < tolerance then dir = across:normalize() end
                -- a section without width has no direction across it: it stays as it is
                if dir:magnitude() > 1e-6 then
                    -- the direction only: the length of the offset unit stays the one of the section (its width factor)
                    local right = dir * cur.right:magnitude()
                    local vertices = {}
                    for j = 1, count do vertices[j] = cur.point + right * offsets[j] end
                    result[i] = { right = right, vertices = vertices }
                end
            end
        end
    end
    return { sections = result }
end

return M
