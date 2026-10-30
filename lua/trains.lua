local M = {}

function M.controlParameters(_, ctx)
    local result, n = {}, #ctx.points
    for i = 1, n do result[i] = n > 1 and (i-1)/(n-1) or 0 end
    return result
end

-- midtown2.exe SHA256 992c53c9250cf822b44bf4a4013bd5805229bbbeb7b478a4c2556531bc5340f3:
-- 57A530 builds half-difference tangents, 57A370 evaluates Hermite; 578A61..578A9F overrides Y.
-- End neighbors wrap (57A6D0/57A710), although the displayed train route is open.
function M.evaluate(_, ctx)
    local points, t = ctx.points, ctx.t
    local n = #points
    if n == 0 then return {position=vec3(0,0,0), tangent=vec3(0,0,0)} end
    if n < 3 then return {position=points[1], tangent=n == 2 and points[2]-points[1] or vec3(0,0,0)} end
    local span = math.min(n-2, math.floor(t*(n-1)))
    local u = t*(n-1)-span
    local a, b = points[(span-1)%n+1], points[span+1]
    local c, d = points[span+2], points[(span+2)%n+1]
    local m0, m1 = (c-a)*0.5, (d-b)*0.5
    local u2, u3 = u*u, u*u*u
    local p = b*(2*u3-3*u2+1)+c*(-2*u3+3*u2)+m0*(u3-2*u2+u)+m1*(u3-u2)
    local tangent = b*(6*u2-6*u)+c*(-6*u2+6*u)+m0*(3*u2-4*u+1)+m1*(3*u2-2*u)
    return {position=vec3(p.x, b.y+(c.y-b.y)*u, p.z), tangent=vec3(tangent.x, c.y-b.y, tangent.z)}
end

return M
