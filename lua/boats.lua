local M = {}

-- A closed loop (ctx.closed): one more control parameter than points, the last (1) is the first point again.
-- Fewer than three points are an open line.
function M.controlParameters(_, ctx)
    local result, n = {}, #ctx.points
    if ctx.closed then
        for i = 1, n + 1 do result[i] = (i-1)/n end
    else
        for i = 1, n do result[i] = n > 1 and (i-1)/(n-1) or 0 end
    end
    return result
end

-- midtown2.exe SHA256 992c53c9250cf822b44bf4a4013bd5805229bbbeb7b478a4c2556531bc5340f3:
-- the sailboat, duck and ferry paths use the same follower as the trains (57A530 builds half-difference tangents,
-- 57A370 evaluates the cubic), whose segment index wraps (57A6D0/57A710) and is never stopped, so the route is a loop
-- from the last point back to the first. Unlike the trains, no code replaces Y: it is cubic like X and Z.
function M.evaluate(_, ctx)
    local points, t = ctx.points, ctx.t
    local n = #points
    if n == 0 then return {position=vec3(0,0,0), tangent=vec3(0,0,0)} end
    if n < 3 then return {position=points[1], tangent=n == 2 and points[2]-points[1] or vec3(0,0,0)} end
    local span, u
    if ctx.closed then
        span = math.min(n-1, math.floor(t*n))
        u = t*n-span
    else
        span = math.min(n-2, math.floor(t*(n-1)))
        u = t*(n-1)-span
    end
    local a, b = points[(span-1)%n+1], points[span%n+1]
    local c, d = points[(span+1)%n+1], points[(span+2)%n+1]
    local m0, m1 = (c-a)*0.5, (d-b)*0.5
    local u2, u3 = u*u, u*u*u
    local p = b*(2*u3-3*u2+1)+c*(-2*u3+3*u2)+m0*(u3-2*u2+u)+m1*(u3-u2)
    local tangent = b*(6*u2-6*u)+c*(-6*u2+6*u)+m0*(3*u2-4*u+1)+m1*(3*u2-2*u)
    return {position=p, tangent=tangent}
end

return M
