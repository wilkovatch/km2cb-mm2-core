local M = {}

function M.canGenerateRails(_, ctx)
    local count = 0
    local seen = {}
    for _, road in ipairs(ctx.neighbors) do
        if road.kind == "road" and road.state.cableCarLine and not seen[road.id] then
            seen[road.id] = true
            count = count + 1
        end
    end
    return count >= 2
end

return M
