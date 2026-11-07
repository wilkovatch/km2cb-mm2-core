using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using TP = CityElements.Types.Parsers.TypeParser;

namespace Api {
    public partial class ApiSelfTest {
        //the post-process pass of the sections ("postProcess" in the settings of a road or custom element spline type)
        async Task SectionPostProcessing() {
            Log("section post-process");

            //the coplanar roads of the core (lua/coplanar.lua)
            Check("the psdl roads make their sections coplanar with a script", TP.GetRoadTypes()["psdl"].postProcessFunction != null);
            //the road is created on the ground, then raised (without its projection)
            async Task<Vector3[][]> Sections(float[][] points, bool coplanar) {
                var id = (await Call("roads.create", new { points = points.Select(p => new { position = p, onGround = false }).ToArray() })).Value<int>();
                await Call("state.setBuiltin", new { @ref = id, name = "project", value = false });
                for (int i = 0; i < points.Length; i++) await Call("roads.movePoint", new { road = id, index = i, position = points[i] });
                await Call("state.setParam", new { @ref = id, name = "makeCoplanar", value = coplanar });
                var road = (Road)History.UndoManager.GetAliveElement(id);
                var res = road.generator.subGen.sectionVertices.Select(v => v.ToArray()).ToArray();
                await Call("roads.delete", new { road = id });
                return res;
            }
            static bool Same(Vector3[][] a, Vector3[][] b) => a.Length == b.Length && a.Zip(b).All(p => p.First.Length == p.Second.Length
                && p.First.Zip(p.Second).All(v => v.First.DistanceTo(v.Second) < 0.0001f));
            //the corners of each section quad on one plane (the four of them, within the tolerance of the core)
            static float Twist(Vector3[][] sections) {
                float max = 0;
                for (int i = 1; i < sections.Length; i++) {
                    var a = sections[i - 1][0]; var b = sections[i - 1][^1]; var c = sections[i][0]; var d = sections[i][^1];
                    var normal = (b - a).Cross(c - a).Normalized();
                    max = Mathf.Max(max, Mathf.Abs(normal.Dot(d - a)));
                }
                return max;
            }
            var slope = new[] { V(-900, 0, -300), V(-850, 15, -260), V(-800, 40, -300) };
            var twisted = await Sections(slope, false);
            var coplanar = await Sections(slope, true);
            Log("twist of the slope: " + Twist(twisted) + ", with make coplanar: " + Twist(coplanar));
            Check("a curved slope has twisted section quads", Twist(twisted) > 0.05f);
            Check("make coplanar flattens them", !Same(twisted, coplanar) && Twist(coplanar) < Twist(twisted) / 2);
            Check("and keeps the first section", coplanar[0].Zip(twisted[0]).All(v => v.First.DistanceTo(v.Second) < 0.0001f));
            var flat = new[] { V(-900, 0, -200), V(-850, 0, -160), V(-800, 0, -200) };
            Check("a flat road is the same with or without it", Same(await Sections(flat, false), await Sections(flat, true)));

            //a custom element spline with its own script (a copy of the decal type)
            var scripts = Path.Combine(folder, "postprocess_lua");
            Directory.CreateDirectory(scripts);
            File.WriteAllText(Path.Combine(scripts, "post.lua"), @"
local M = {}
function M.raise(v, ctx)
    if #ctx.controls.points ~= 3 or ctx.closed or ctx.state.width ~= 3 or ctx.instanceState ~= nil or #ctx.sections[1].offsets ~= 2 then
        error('unexpected context')
    end
    local res = {}
    for i, s in ipairs(ctx.sections) do
        local vertices = {}
        for j, p in ipairs(s.vertices) do vertices[j] = p + vec3(0, 1, 0) end
        res[i] = { point = s.point + vec3(0, 1, 0), vertices = vertices }
    end
    return { sections = res }
end
function M.none(v, ctx) return nil end
function M.wrongCount(v, ctx) return { sections = { [1] = { vertices = { vec3(0, 0, 0) } } } } end
function M.typo(v, ctx) return { sections = { [1] = { verticse = {} } } } end
function M.outOfRange(v, ctx) return { sections = { [99] = { point = vec3(0, 0, 0) } } } end
function M.fails(v, ctx) error('broken') end
return M");
            using var host = RuntimeCalculator.Scripting.LuaScriptHost.CreateForFolder(scripts);
            var types = TP.GetCustomElementTypes();
            const string key = "__testSectionPostProcess";
            int id = -1;
            async Task<CustomElement> Create(string function) {
                var source = JsonConvert.DeserializeObject<CityElements.Types.CustomElementType>(JsonConvert.SerializeObject(types["decal"].typeData));
                var settings = source.settings.spline;
                settings.projectPoints = settings.projectSections = false;
                settings.maxSectionLength = 0; settings.splitCondition = null;
                settings.postProcess = "post." + function;
                types[key] = new CityElements.Types.Runtime.CustomElementType(source, key, host);
                id = (await Call("customElement.create", new { type = key, state = new { width = 3, texture = "texture/decal_zigzag_l.tex", curveType = 2 },
                    points = new { spline = new[] { new { position = new[] { 600, 0, 600 } }, new { position = new[] { 600, 0, 610 } }, new { position = new[] { 600, 0, 620 } } } } })).Value<int>();
                return (CustomElement)History.UndoManager.GetAliveElement(id);
            }
            async Task Delete() {
                if (id >= 0) await Call("customElement.delete", new { element = id });
                id = -1;
            }
            static bool Raised1(CustomElement e) => e.splineData.sections.Length == 3
                && e.splineData.sections.All(s => Mathf.Abs(s.center[1] - 1) < 0.0001f && s.vertices.All(v => Mathf.Abs(v[1] - 1) < 0.0001f));
            static bool OnGround(CustomElement e) => e.splineData.sections.Length == 3
                && e.splineData.sections.All(s => Mathf.Abs(s.center[1]) < 0.0001f && s.vertices.All(v => Mathf.Abs(v[1]) < 0.0001f));
            static float[] MeshY(CustomElement e) => e.generator.m.SurfaceGetArrays(0)[(int)Mesh.ArrayType.Vertex].AsVector3Array().Select(v => v.Y).ToArray();
            try {
                var element = await Create("none");
                Check("returning nil changes nothing", OnGround(element) && host.ErrorCount == 0);
                var groundY = MeshY(element);
                await Delete();
                element = await Create("raise");
                Check("a spline post-process gets its context and edits the exported sections", Raised1(element) && host.ErrorCount == 0);
                var raisedY = MeshY(element);
                Check("and the mesh made from them", raisedY.Length > 0 && raisedY.Length == groundY.Length && raisedY.Zip(groundY).All(p => Mathf.Abs(p.First - p.Second - 1) < 0.0001f));
                await Delete();
                foreach (var function in new[] { "wrongCount", "typo", "outOfRange", "fails" }) {
                    var errors = host.ErrorCount;
                    Check("an invalid post-process (" + function + ") is reported and leaves the sections as they are", OnGround(await Create(function)) && host.ErrorCount == errors + 1);
                    await Delete();
                }
            } finally {
                await Delete();
                types.Remove(key);
            }
        }
    }
}
