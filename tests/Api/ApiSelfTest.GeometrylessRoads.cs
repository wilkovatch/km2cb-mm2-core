using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using Newtonsoft.Json.Linq;
using GO = GameEngine.GameObject;
using TP = CityElements.Types.Parsers.TypeParser;

namespace Api {
    public partial class ApiSelfTest {
        //the roads without geometry (RoadSettings.geometryless, the bai road type of the core): no meshes, left out of the
        //surface of their intersections (sized against the other roads, without changing them), an intersection with only
        //them has no surface, and their traffic goes in the BAI in the rooms they lie over
        async Task GeometrylessRoads() {
            Log("geometry-less roads");
            var types = TP.GetRoadTypes();
            Check("the bai road type has no geometry", types.ContainsKey("bai") && types["bai"].typeData.settings.geometryless);
            Road R(int id) => (Road)History.UndoManager.GetAliveElement(id);
            static int Vertices(ArrayMesh m) => Enumerable.Range(0, m.GetSurfaceCount()).Sum(s => m.SurfaceGetArrayLen(s));
            object End(int road, string end = "end") => new { roadEnd = new { road, end } };
            bool Picks(Node3D node, object element, float x, float z) {
                return GameEngine.Raycast.DoPickRaycast(node, new Vector3(x, 30, z), Vector3.Down, out var hit, 60, 1 << 7)
                    && ElementPlacer.ReferencePicker.ElementOf(hit.collider) == element;
            }

            //Create -> Road, then the type changed to BAI-only before placing any point (its panel has no intersection group)
            {
                const System.Reflection.BindingFlags flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
                T Field<T>(object obj, string name) => (T)obj.GetType().GetField(name, flags).GetValue(obj);
                typeof(CityBuilderMenuBar).GetMethod("CreateRoad", flags).Invoke(builder, null);
                await Frames(2);
                var panel = Field<EditorPanels.RoadEditorPanel>(builder, "roadEditorPanel");
                var complex = (System.Collections.IDictionary)typeof(EditorPanel).GetField("complexElements", flags).GetValue(panel);
                var selector = complex.Values.Cast<object>().Single(c => c.GetType().Name.StartsWith("TypeSelector"));
                Exception error = null;
                try {
                    Field<EditorPanelElements.Dropdown>(selector, "typeDropdown").SetValue(Field<List<string>>(selector, "typesIndex").IndexOf("bai"));
                } catch (Exception e) { error = e; }
                await Frames(2); //the controls of the previous type are freed
                try {
                    panel.Update(); //as after every change of the city
                } catch (Exception e) { error ??= e; }
                Check("a new road can be switched to BAI-only before placing its points" + (error != null ? " (" + error.Message + ")" : ""), error == null && panel.ActiveSelf());
                builder.CloseAllPanels();
                builder.SetSelectObjectMode();
                await Frames(2);
            }

            //a square of BAI-only roads: four intersections without surface
            const float a = -380, b = -220;
            var r1 = (await Call("roads.create", new { type = "bai", points = new[] { Pos(a, a), Pos(b, a) } })).Value<int>();
            var r2 = (await Call("roads.create", new { type = "bai", points = new object[] { End(r1), Pos(b, b) } })).Value<int>();
            var r3 = (await Call("roads.create", new { type = "bai", points = new object[] { End(r2), Pos(a, b) } })).Value<int>();
            var r4 = (await Call("roads.create", new { type = "bai", points = new object[] { End(r3), End(r1, "start") } })).Value<int>();
            await Call("city.flush");
            await Frames(3);
            var square = new[] { r1, r2, r3, r4 }.Select(R).ToList();
            var corners = square.Select(r => r.endIntersection).ToList();
            Check("the BAI-only roads have no mesh", square.All(r => r.generator.m.GetSurfaceCount() == 0 && r.generator.geometryless));
            Check("but their traffic lanes", square.All(r => r.generator.lanesRenderersContainer != null && GO.GetChildCount(r.generator.lanesRenderersContainer) > 0));
            Check("their intersections have no surface", corners.All(i => i != null && i.geometryless && i.generator.m.GetSurfaceCount() == 0 && i.generator.partsInfo.Count == 0));
            Check("their ends are still away from the centre of the intersections", corners.All(i => i.sizes.Count == 2 && i.sizes.All(s => s > 1)));
            Check("the intersections have all their roads in order, none with geometry", corners.All(i => i.generator.sortOrder.Count == 2 && i.generator.geometrySortOrder.Count == 0));
            builder.CloseAllPanels();
            M.ProcessUpdate();
            Check("their lines are shown without being selected", square.All(r => r.generator.lr.enabled));
            Check("a BAI-only road can be picked", Picks(R(r1), R(r1), (a + b) / 2, a));
            Check("and an intersection without surface", Picks(corners[0].geo, corners[0], b, a));
            //zoomed to (as from the validation panel), and edited (a screenshot of the road with its panel)
            Check("the camera can zoom to an intersection without surface", (await Send("view.focus", new { @ref = History.ElementRegistry.GetId(corners[0]) }))["error"] == null);
            await Call("view.focus", new { @ref = r1 });
            if (DisplayServer.GetName() != "headless") {
                History.UndoManager.Record("edit BAI-only road", () => builder.SelectObject(R(r1), true, null));
                await Frames(10);
                Screenshot("geometryless_roads_selected.png");
                builder.CloseAllPanels();
                M.ProcessUpdate();
                Check("its lanes are hidden again when it's not selected", !GO.GetEnabled(R(r1).generator.lanesRenderersContainer) && R(r1).generator.lr.enabled);
            }

            //an intersection of PSDL roads: a BAI-only road changes neither the sizes of the others nor the surface
            const float cx = -50, cz = -300;
            var p1 = (await Call("roads.create", new { type = "psdl", points = new[] { Pos(cx - 80, cz), Pos(cx, cz) } })).Value<int>();
            var p2 = (await Call("roads.create", new { type = "psdl", points = new object[] { End(p1), Pos(cx + 80, cz) } })).Value<int>();
            var cross = R(p1).endIntersection;
            var p3 = (await Call("roads.create", new { type = "psdl", points = new object[] { new { intersection = History.ElementRegistry.GetId(cross) }, Pos(cx, cz + 80) } })).Value<int>();
            await Call("city.flush");
            var sizes = cross.sizes.ToList();
            var surface = Vertices(cross.generator.m);
            var bai = (await Call("roads.create", new { type = "bai", points = new object[] { new { intersection = History.ElementRegistry.GetId(cross) }, Pos(cx, cz - 80) } })).Value<int>();
            await Call("city.flush");
            Check("a BAI-only road on a PSDL intersection keeps the sizes of the other roads", cross.roads.Count == 4
                && Enumerable.Range(0, 3).All(i => Mathf.Abs(cross.sizes[i] - sizes[i]) < 0.001f) && cross.sizes[3] > 1);
            Check("and its surface (" + surface + " vertices)", surface > 0 && Vertices(cross.generator.m) == surface && !cross.geometryless);
            Check("the surface is between the PSDL roads", cross.generator.sortOrder.Count == 4 && cross.generator.geometrySortOrder.Count == 3
                && !cross.generator.geometrySortOrder.Contains(cross.roads.IndexOf(R(bai))));
            await CheckUndo("road type changed to BAI-only", () => Call("state.setType", new { @ref = p3, type = "bai" }));
            await Call("city.flush");
            Check("a PSDL road changed to BAI-only leaves the surface", cross.generator.geometrySortOrder.Count == 2 && R(p3).generator.m.GetSurfaceCount() == 0);
            await Call("state.setType", new { @ref = p3, type = "psdl" });
            await Call("city.flush");
            Check("and changed back gives it the same surface", cross.generator.geometrySortOrder.Count == 3 && Vertices(cross.generator.m) == surface);

            //the same road with and without geometry (for the exporter check), and a BAI-only road over no room
            async Task<int> Twin(string type, float z) {
                var id = (await Call("roads.create", new { type, points = new[] { Pos(100, z), Pos(150, z + 10), Pos(200, z) } })).Value<int>();
                await Call("elements.rename", new { @ref = id, name = "Twin " + type });
                foreach (var (name, value) in new (string, object)[] { ("isDouble", true), ("hasSidewalks", true), ("totalWidth", 16.0), ("roadWidth", 11.0),
                    ("forwardLanes", 2), ("backwardLanes", 1), ("divider", 1), ("dividerWidth", 1.5), ("makeCoplanar", false) }) {
                    if (name != "makeCoplanar" || type == "psdl") await Call("state.setParam", new { @ref = id, name, value });
                }
                return id;
            }
            await Twin("psdl", -380);
            await Twin("bai", -330);
            var lonely = (await Call("roads.create", new { type = "bai", points = new[] { Pos(100, -150), Pos(200, -150) } })).Value<int>();
            await Call("elements.rename", new { @ref = lonely, name = "Lonely BAI road" });
            //the ground under the square: a room for its roads and intersections
            await Call("patches.create", new { perimeter = new[] { Pos(a - 30, a - 30), Pos(b + 30, a - 30), Pos(b + 30, b + 30), Pos(a - 30, b + 30) } });
            await Call("city.flush");
            if (DisplayServer.GetName() != "headless") {
                //the square over its patch and the PSDL intersection with its BAI-only road, from above, with the lines
                await Call("view.render", new { camera = "top", elements = new[] { r1, r2, r3, r4, p1, p2, p3, bai }, width = 800, height = 500,
                    layers = new[] { "terrain", "geometry", "helpers" }, path = Path.Combine(folder, "..", "geometryless_roads.png") });
            }

            var jsonPath = Path.Combine(folder, "..", "geometryless_export.json");
            await Call("city.exportJson", new { path = jsonPath });
            var json = JObject.Parse(File.ReadAllText(jsonPath));
            var exported = json["roads"].First(r => r["data"]["name"].Value<string>() == GO.GetName(R(r1)))["data"]["fields"];
            Check("the export says which roads have no geometry, with their section vertices", exported["geometryless"]?.Value<bool>() == true
                && exported["sectionVertexCount"]?.Value<int>() == 7 && exported["b64v3a_sectionVertices"] != null);
            var exportedCorner = json["intersections"].First(i => i["data"]["name"].Value<string>() == GO.GetName(corners[0].geo))["data"]["fields"];
            Check("and which intersections", exportedCorner["geometryless"]?.Value<bool>() == true && ((JArray)exportedCorner["geometrySortOrder"]).Count == 0);

            //the exporter (dry export): no errors from these elements, warnings for the shared room and the road over no room
            var res = await Call("city.validate");
            var items = ((JArray)res["items"]).OfType<JObject>().ToList();
            var names = new HashSet<string>(square.Select(GO.GetName).Concat(corners.Select(i => GO.GetName(i.geo))).Append("Lonely BAI road").Append(GO.GetName(cross.geo)));
            foreach (var item in items) Log("     " + item["level"] + ": " + item["element"]?["name"] + ": " + item["message"]);
            Check("the export has no errors on the elements without geometry", !items.Any(i => i["level"]?.Value<string>() == "error" && names.Contains(i["element"]?["name"]?.Value<string>() ?? "")));
            Check("a BAI-only road over no room is a warning", items.Any(i => i["level"]?.Value<string>() == "warning" && i["element"]?["name"]?.Value<string>() == "Lonely BAI road"));
            Check("intersections without geometry sharing a room are a warning", items.Count(i => i["level"]?.Value<string>() == "warning"
                && corners.Any(c => GO.GetName(c.geo) == i["element"]?["name"]?.Value<string>())) == 3);

            //the exporter itself: the BAI of the roads without geometry as the one of the same PSDL road, in the rooms under them
            var python = Path.Combine(PathHelper.BasePath(), "python", "python.exe");
            var tool = Path.Combine(PathHelper.BasePath(), "Files", "cores", "MidtownMadness2", "exporters", "psdl", "tools", "_test_geometryless_roads.py");
            if (!File.Exists(python)) {
                Log("     no bundled Python: the exporter check is skipped");
            } else {
                var info = new System.Diagnostics.ProcessStartInfo(python, "-I \"" + tool + "\"") {
                    RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false, CreateNoWindow = true
                };
                info.Environment["KM2_GEOMETRYLESS_JSON"] = Path.GetFullPath(jsonPath);
                using var process = System.Diagnostics.Process.Start(info);
                var output = process.StandardOutput.ReadToEndAsync();
                var errors = process.StandardError.ReadToEndAsync();
                await Task.Run(() => process.WaitForExit());
                if (process.ExitCode != 0) Log("     " + await output + await errors);
                Check("the exporter gives the BAI-only roads the BAI of the same PSDL roads, in the rooms under them", process.ExitCode == 0);
            }

            foreach (var id in new[] { r1, r2, r3, r4, p1, p2, p3, bai, lonely }) {
                if (History.UndoManager.GetAliveElement(id) != null) await Call("roads.delete", new { road = id });
            }
        }
    }
}
