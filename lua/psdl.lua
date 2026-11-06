-- Helpers for the elements exported to the PSDL.

local M = {}

-- Only the double roads have a low LOD texture (the exporter writes just the main texture of the others), and it needs
-- their road texture (see converters/generateLodTexture)
function M.canGenerateLodTexture(_, ctx)
    local state = ctx.element.state
    return state.isDouble == true and state.texture1 ~= nil and state.texture1 ~= ""
end

return M
