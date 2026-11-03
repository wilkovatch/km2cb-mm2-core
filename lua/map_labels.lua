-- Smooth, filled core geometry from the same bundled font used by the menu-map exporter.
local F = require("map_label_font")
local M = {}

-- The same values as the exporter (hudmap_export.py).
local DEFAULT_SIZE = 6.75
local TRACKING = 0.12
-- The editor look, not a preview of the exported map: readable over anything in the 3D city.
local TEXT_COLOR = vec3(1, 1, 1)
local OUTLINE_COLOR = vec3(0, 0, 0)
local OUTLINE_WIDTH = 0.05 -- in em
local OUTLINE_DROP = 0.02 -- in metres, under the text where the outline of a letter reaches the next one
local TEXT_HEIGHT = 5
local ROUND_JOIN_DOT = 0.92 -- how far apart two outline normals can be without another point between them

local function codes(text)
    local result, i = {}, 1
    while i <= #text do
        local cp = string.byte(text, i)
        local count = cp >= 240 and cp <= 244 and 4 or cp >= 224 and cp <= 239 and 3 or cp >= 194 and cp <= 223 and 2 or 1
        if count > 1 then
            local valid = i + count - 1 <= #text
            for j=1,count-1 do
                local b=string.byte(text,i+j)
                if not b or b < 128 or b > 191 then valid=false end
            end
            if valid then
                cp = cp % 2^(7-count)
                for j=1,count-1 do cp=cp*64+string.byte(text,i+j)-128 end
                i=i+count-1
            end
        elseif cp >= 55296 and cp <= 56319 then
            local low=string.byte(text,i+1)
            if low and low >= 56320 and low <= 57343 then cp=65536+(cp-55296)*1024+low-56320; i=i+1 end
        end
        for _, upper in ipairs(F.upper[cp] or {cp}) do result[#result+1]=upper end
        i=i+1
    end
    return result
end

-- A strip around the edges used by one triangle only, with round joins at the outer corners. The triangles of the glyphs
-- are clockwise, so the outside of an edge is on its left; the new triangles are clockwise too, to face up like them.
local function buildOutline(glyph)
    local vertices, triangles = {}, {}
    local function vertex(x, y)
        vertices[#vertices+1]=x
        vertices[#vertices+1]=y
        return #vertices/2-1
    end
    local function position(index)
        return glyph.v[2*index+1], glyph.v[2*index+2]
    end
    local count = #glyph.v/2
    local used = {}
    for i=1,#glyph.t,3 do
        for j=0,2 do
            local a,b=glyph.t[i+j],glyph.t[i+(j+1)%3]
            local key=math.min(a,b)*count+math.max(a,b)
            used[key]=(used[key] or 0)+1
        end
    end
    for i=1,count do vertex(glyph.v[2*i-1], glyph.v[2*i]) end -- the same indices as the glyph
    local edges, leaving = {}, {}
    for i=1,#glyph.t,3 do
        for j=0,2 do
            local a,b=glyph.t[i+j],glyph.t[i+(j+1)%3]
            if used[math.min(a,b)*count+math.max(a,b)] == 1 then
                local ax,ay=position(a)
                local bx,by=position(b)
                local dx,dy=bx-ax,by-ay
                local length=math.sqrt(dx*dx+dy*dy)
                if length > 0 then
                    local nx,ny=-dy/length,dx/length
                    local outerA=vertex(ax+nx*OUTLINE_WIDTH,ay+ny*OUTLINE_WIDTH)
                    local outerB=vertex(bx+nx*OUTLINE_WIDTH,by+ny*OUTLINE_WIDTH)
                    for _,index in ipairs({a,outerA,b,b,outerA,outerB}) do triangles[#triangles+1]=index end
                    local edge={a=a,b=b,nx=nx,ny=ny,outerA=outerA,outerB=outerB}
                    leaving[a]=edge
                    edges[#edges+1]=edge
                end
            end
        end
    end
    local function join(center, nx1, ny1, outer1, nx2, ny2, outer2)
        local cx,cy=position(center)
        local mx,my=nx1+nx2,ny1+ny2
        local length=math.sqrt(mx*mx+my*my)
        if nx1*nx2+ny1*ny2 >= ROUND_JOIN_DOT or length < 1e-6 then
            for _,index in ipairs({center,outer1,outer2}) do triangles[#triangles+1]=index end
            return
        end
        mx,my=mx/length,my/length
        local middle=vertex(cx+mx*OUTLINE_WIDTH,cy+my*OUTLINE_WIDTH)
        join(center,nx1,ny1,outer1,mx,my,middle)
        join(center,mx,my,middle,nx2,ny2,outer2)
    end
    for _,edge in ipairs(edges) do
        local following=leaving[edge.b]
        -- turning right the outer points move apart, turning left the strips of the two edges overlap
        if following and edge.nx*following.ny-edge.ny*following.nx < 0 then
            join(edge.b,edge.nx,edge.ny,edge.outerB,following.nx,following.ny,following.outerA)
        end
    end
    return {v=vertices,t=triangles}
end

local outlines = {}
local function outlineOf(cp, glyph)
    if not outlines[cp] then outlines[cp]=buildOutline(glyph) end
    return outlines[cp]
end

function M.geometry(v, ctx)
    local text = string.gsub(ctx.parameters.text or "", "^%s*(.-)%s*$", "%1")
    local vertices, triangles, outerVertices, outerTriangles = {}, {}, {}, {}
    local advance, previous = 0, nil
    local minx, miny, maxx, maxy = math.huge, math.huge, -math.huge, -math.huge
    for _, cp in ipairs(codes(text)) do
        local glyph=F.glyphs[cp] or F.glyphs[0]
        if previous then advance=advance+(F.kern[previous..":"..cp] or 0)+TRACKING end
        local offset=#vertices
        for i=1,#glyph.v,2 do
            local x,y=advance+glyph.v[i],glyph.v[i+1]
            vertices[#vertices+1]={x,y}
            minx,miny,maxx,maxy=math.min(minx,x),math.min(miny,y),math.max(maxx,x),math.max(maxy,y)
        end
        for _,index in ipairs(glyph.t) do triangles[#triangles+1]=offset+index end
        local outline=outlineOf(F.glyphs[cp] and cp or 0, glyph)
        local outerOffset=#outerVertices
        for i=1,#outline.v,2 do outerVertices[#outerVertices+1]={advance+outline.v[i],outline.v[i+1]} end
        for _,index in ipairs(outline.t) do outerTriangles[#outerTriangles+1]=outerOffset+index end
        advance,previous=advance+glyph.a,cp
    end
    local size = v.size > 0 and v.size or DEFAULT_SIZE
    local scale = v._GLOBAL_hudmapMetersPerPixel > 0 and v._GLOBAL_hudmapMetersPerPixel or 5.5
    local center = ctx.points.center
    local c,s=math.cos(math.rad(v.angle)),math.sin(math.rad(v.angle))
    local meshes = {}
    if #vertices > 0 then
        local cx,cy=(minx+maxx)/2,(miny+maxy)/2
        local function place(source, height)
            local result={}
            for _,p in ipairs(source) do
                local x,y=(p[1]-cx)*size*scale,(p[2]-cy)*size*scale
                result[#result+1]=center+vec3(-c*x+s*y,height,-s*x-c*y)
            end
            return result
        end
        meshes={
            {color=TEXT_COLOR,vertices=place(vertices,TEXT_HEIGHT),triangles=triangles},
            {color=OUTLINE_COLOR,vertices=place(outerVertices,TEXT_HEIGHT-OUTLINE_DROP),triangles=outerTriangles}
        }
    end
    -- The centre marker stays at its authored position.
    return {meshes=meshes,lines={
        {points={center+vec3(-1,0.4,0),center+vec3(1,0.4,0)},color="yellow",always=true},
        {points={center+vec3(0,0.4,-1),center+vec3(0,0.4,1)},color="yellow",always=true}
    }}
end
return M
