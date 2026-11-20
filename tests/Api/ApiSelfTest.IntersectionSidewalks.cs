using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using Newtonsoft.Json.Linq;
using GO = GameEngine.GameObject;

namespace Api {
    public partial class ApiSelfTest {
        //the segments of the sidewalks of the intersections: the inner and outer sides with different segments (joined by
        //a strip with repeated vertices), the outer side skipping the crosswalks, the overrides of single sidewalks (kept by
        //the road they start at), their list and outlines in the panel, and the road-style UV only where the sides match
        async Task IntersectionSidewalks() {
            Log("intersection sidewalks");
            object End(int road, string end = "end") => new { roadEnd = new { road, end } };
            var rA = (await Call("roads.create", new { points = new[] { Pos(500, 600), Pos(700, 600) } })).Value<int>();
            var rB = (await Call("roads.create", new { points = new object[] { Pos(700, 800), Pos(705, 700), End(rA) } })).Value<int>();
            var id = (await Derived(rA))["endIntersection"].Value<int>();
            var rC = (await Call("roads.create", new { points = new object[] { Pos(900, 600), Pos(800, 605), new { intersection = id } } })).Value<int>();
            var intersection = (Intersection)History.UndoManager.GetAliveElement(id);
            await Call("state.setBuiltin", new { @ref = id, name = "sidewalkSegments", value = 4 });
            async Task<JArray> Sidewalks() => (JArray)(await Derived(id))["sidewalks"];
            JToken Of(JArray sidewalks, int road) => sidewalks.First(s => s["road"].Value<int>() == road);
            //the vertices of the sidewalk surfaces
            List<Vector3> JunctionVertices() {
                var res = new List<Vector3>();
                var gen = intersection.generator;
                for (int s = 0; s < gen.m.GetSurfaceCount() && s < gen.partsInfo.Count; s++) {
                    if (!gen.partsInfo[s].StartsWith("junction_")) continue;
                    res.AddRange((Vector3[])gen.m.SurfaceGetArrays(s)[(int)Mesh.ArrayType.Vertex]);
                }
                return res;
            }

            var sw = await Sidewalks();
            Check("an intersection of three roads has three sidewalks", sw.Count == 3);
            Check("by default the two sides of the sidewalks match (inner segments + 3 sections)",
                sw.All(s => s["sidesMatch"].Value<bool>() && s["sections"].Value<int>() == 7 && s["outerSegments"].Value<int>() == 4 && !s["overridden"].Value<bool>()));
            var legacy = JunctionVertices();
            await Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSegments", value = 4 });
            var same = JunctionVertices();
            Check("outer segments equal to the inner ones give the same sidewalks as before", legacy.Count > 0 && same.Count == legacy.Count
                && legacy.Zip(same).All(p => p.First.DistanceTo(p.Second) < 1e-4f));

            await CheckUndo("outer segments of the sidewalks", () => Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSegments", value = 2 }));
            sw = await Sidewalks();
            //inner stations 0, 1, 1.25, 1.5, 1.75, 2, 3, outer ones 0, 1, 1.5, 2, 3: those of the outer side are among them
            Check("fewer outer segments: the sides don't match, the sections are those of the inner side",
                sw.All(s => !s["sidesMatch"].Value<bool>() && s["outerSegments"].Value<int>() == 2 && s["sections"].Value<int>() == 7));
            Check("and the outer vertices repeat", JunctionVertices().Count == legacy.Count && !legacy.Zip(JunctionVertices()).All(p => p.First.DistanceTo(p.Second) < 1e-4f));
            await Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSegments", value = 6 });
            sw = await Sidewalks();
            //outer stations 1 + k/6: 1.5 is shared, 1.1667, 1.3333, 1.6667, 1.8333 added to the 7 of the inner side
            Check("more outer segments: a section for each station of either side", sw.All(s => !s["sidesMatch"].Value<bool>() && s["sections"].Value<int>() == 11));

            await CheckUndo("outer side skipping the crosswalks", () => Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSkipsCrosswalks", value = true }));
            await Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSegments", value = 1 });
            sw = await Sidewalks();
            Check("one outer segment skipping the crosswalks: a straight outer side, the sections of the inner side",
                sw.All(s => !s["sidesMatch"].Value<bool>() && s["outerSkipsCrosswalks"].Value<bool>() && s["sections"].Value<int>() == 7));
            Check("the outlines of the sidewalks have the outer side as a single edge", intersection.generator.sidewalks.All(s => s.outline.Count <= 2 + 7));
            if (DisplayServer.GetName() != "headless") {
                await Call("view.camera.set", new { position = V(700, 30, 580), target = V(700, 0, 605) });
                await Frames(5);
                Screenshot("intersection_sidewalks_chamfer.png");
            }
            await Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSkipsCrosswalks", value = false });
            await Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSegments", value = 0 });
            sw = await Sidewalks();
            Check("outer segments 0: as the inner ones again", sw.All(s => s["sidesMatch"].Value<bool>() && s["sections"].Value<int>() == 7));

            //a single sidewalk with its own segments, kept by its road
            await CheckUndo("sidewalk override", () => Call("intersections.setSidewalkOverride", new { intersection = id, road = rC, outerSegments = 2 }));
            sw = await Sidewalks();
            Check("the overridden sidewalk has its own segments, the others those of the intersection",
                Of(sw, rC)["overridden"].Value<bool>() && Of(sw, rC)["outerSegments"].Value<int>() == 2 && Of(sw, rC)["innerSegments"].Value<int>() == 4
                && !Of(sw, rC)["sidesMatch"].Value<bool>() && sw.Count(s => s["overridden"].Value<bool>()) == 1);
            var data = (await Call("elements.get", new { @ref = id }))["data"];
            Check("the override is in the instance state", data.SelectToken("instanceState.sidewalks")?.Count() == 1);
            await Call("intersections.setSidewalkOverride", new { intersection = id, road = rC, innerSegments = 3 });
            sw = await Sidewalks();
            Check("the values not given are kept", Of(sw, rC)["outerSegments"].Value<int>() == 2 && Of(sw, rC)["innerSegments"].Value<int>() == 3);
            var loose = (await Call("roads.create", new { points = new[] { Pos(500, 900), Pos(600, 900) } })).Value<int>();
            await Expect("an override for a road not on the intersection", "invalid_operation", "intersections.setSidewalkOverride", new { intersection = id, road = loose, outerSegments = 2 });

            //the panel: the list of the sidewalks, the selected one picked from the view, its override
            const System.Reflection.BindingFlags flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
            History.UndoManager.Record("edit intersection", () => builder.SelectObject(intersection.geo, true, null));
            await Frames(3);
            var panel = (EditorPanels.IntersectionEditorPanel)typeof(CityBuilderMenuBar).GetField("intersectionEditorPanel", flags).GetValue(builder);
            T Field<T>(string name) => (T)typeof(EditorPanels.IntersectionEditorPanel).GetField(name, flags).GetValue(panel);
            Check("the click mode of an edited intersection picks its sidewalks", builder.terrainClick.modifier is ElementPlacer.SidewalkPicker);
            Check("the panel lists the sidewalks", Field<List<int>>("listedSidewalks").Count == 3);
            var first = intersection.generator.sidewalks[0];
            var outer = first.outline[1];
            var inner = first.outline[first.outline.Count - 2];
            var inside = (outer + inner) * 0.5f;
            Check("a point of a sidewalk is found in it", intersection.generator.FindSidewalk(inside) == 0);
            Check("the centre of the intersection is in no sidewalk", intersection.generator.FindSidewalk(GO.GetPosition(intersection.point), 0.1f) == -1);
            panel.PickSidewalk(0);
            await Frames(2);
            Check("picking a sidewalk selects it and shows its tab", Field<int>("curSidewalkRoad") == first.road && Field<List<GameEngine.LineRenderer>>("outlines").Count == 3);
            if (DisplayServer.GetName() != "headless") {
                //a click on another sidewalk in the view selects it (the click mode of the edited intersection)
                await Call("view.camera.set", new { position = V(700, 30, 580), target = V(700, 0, 605) });
                await Frames(4);
                var other = intersection.generator.sidewalks[1];
                var screen = GetViewport().GetCamera3D().UnprojectPosition(GameEngine.Vector3.DecodePosition((other.outline[1] + other.outline[other.outline.Count - 2]) * 0.5f));
                GameEngine.Input.WarpMouse(GetViewport(), screen);
                await Frames(3);
                Input.ParseInputEvent(new InputEventMouseButton { ButtonIndex = MouseButton.Left, Pressed = true, Position = screen, GlobalPosition = screen });
                await Frames(2);
                Input.ParseInputEvent(new InputEventMouseButton { ButtonIndex = MouseButton.Left, Pressed = false, Position = screen, GlobalPosition = screen });
                await Frames(4);
                Check("clicking a sidewalk in the view selects it", Field<int>("curSidewalkRoad") == other.road && panel.ActiveSelf());
                panel.PickSidewalk(0);
                await Frames(2);
            }
            var overrideCheckbox = Field<EditorPanelElements.Checkbox>("swOverrideCheckbox");
            Check("its override checkbox shows it has none", overrideCheckbox.GetInteractable() && !overrideCheckbox.GetValue());
            if (DisplayServer.GetName() != "headless") {
                //(through the operations: the API closes the panels)
                var shown = new ObjectState();
                shown.SetInt("innerSegments", 8);
                shown.SetInt("outerSegments", 2);
                Operations.Intersections.SetSidewalkOverride(intersection, first.road, shown);
                M.FlagAsChanged();
                M.ProcessUpdate();
                panel.Update();
                await Call("view.camera.set", new { position = V(700, 30, 580), target = V(700, 0, 605) });
                await Frames(5);
                Screenshot("intersection_sidewalks_panel.png");
                Operations.Intersections.SetSidewalkOverride(intersection, first.road, null);
                M.FlagAsChanged();
                M.ProcessUpdate();
                panel.Update();
            }
            typeof(EditorPanels.IntersectionEditorPanel).GetMethod("SetSidewalkOverridden", flags).Invoke(panel, new object[] { true });
            M.ProcessUpdate();
            Check("overriding it from the panel copies the segments of the intersection", Operations.Intersections.GetSidewalkOverride(intersection, first.road)?.Int("innerSegments") == 4
                && Field<EditorPanelElements.InputField>("swOuterField").GetInteractable());
            builder.CloseAllPanels();
            builder.SetSelectObjectMode();
            await Frames(2);
            Check("the outlines go with the panel", Field<List<GameEngine.LineRenderer>>("outlines").Count == 0);

            //the override follows its road when an earlier road of the intersection is removed
            var keyC = intersection.roads.IndexOf((Road)History.UndoManager.GetAliveElement(rC));
            var keyB = intersection.roads.IndexOf((Road)History.UndoManager.GetAliveElement(rB));
            await Call("intersections.setSidewalkOverride", new { intersection = id, road = rB, outerSegments = 5 });
            await CheckUndo("road with a sidewalk override deleted", () => Call("roads.delete", new { road = rB }));
            sw = await Sidewalks();
            Check("removing a road drops its override and keeps the others on their roads (" + keyB + " < " + keyC + ")", keyB < keyC
                && Of(sw, rC)["overridden"].Value<bool>() && Of(sw, rC)["innerSegments"].Value<int>() == 3
                && ((JArray)(await Call("elements.get", new { @ref = id }))["data"].SelectToken("instanceState.sidewalks")).Count == 2);
            await Call("intersections.setSidewalkOverride", new { intersection = id, road = rC, clear = true });
            Check("clearing the override", !Of(await Sidewalks(), rC)["overridden"].Value<bool>());

            //the road-style UV is available only while the sides match, and exported only for the sidewalks where they do
            await Call("state.setParam", new { @ref = id, name = "fixSidewalksUV", value = true });
            Check("the road-style UV is available with matching sides", CoreElementTool.Evaluate("sidewalks.roadStyleUVAvailable", intersection, "test"));
            await Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSegments", value = 2 });
            Check("but not with other outer segments", !CoreElementTool.Evaluate("sidewalks.roadStyleUVAvailable", intersection, "test"));
            await Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSegments", value = 0 });
            await Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSkipsCrosswalks", value = true });
            Check("nor with the outer side skipping the crosswalks", !CoreElementTool.Evaluate("sidewalks.roadStyleUVAvailable", intersection, "test"));
            await Call("state.setBuiltin", new { @ref = id, name = "sidewalkOuterSkipsCrosswalks", value = false });
            await Call("intersections.setSidewalkOverride", new { intersection = id, road = rC, outerSegments = 2 });
            using var geometry = new CityEncoder.ExportGeometry(History.ElementRegistry.GetId);
            var exported = geometry.GetIntersection(intersection, id);
            var matches = exported.data.fields.Array<bool>("sidewalksMatch");
            Check("the export says which sidewalks match", matches != null && matches.Length == 2 && matches.Count(m => !m) == 1);
            //a dry export: the PSDL writer takes the road-style sidewalk and the one with repeated outer vertices
            var res = await Call("city.validate");
            var name = GO.GetName(intersection.geo);
            Log("     city.validate: " + res["errors"] + " errors, " + res["warnings"] + " warnings in " + res["durationMs"].Value<double>().ToString("0") + " ms");
            var errors = ((JArray)res["items"]).Where(i => i["level"].Value<string>() == "error" && i["element"]?["name"]?.Value<string>() == name).ToList();
            Check("the intersection exports without errors" + (errors.Count > 0 ? " (" + errors[0]["message"] + ")" : ""), errors.Count == 0);
        }
    }
}
