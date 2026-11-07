using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using Newtonsoft.Json.Linq;

namespace Api {
    public partial class ApiSelfTest {
        //The rails (the RAILC attributes of the rooms): splines whose points go only on the perimeters of the PSDL patches, roads
        //and intersections (the Lua acceptTarget of the type), with the spans following the perimeter between them (dynamic
        //followConnections). Needs the roads of Roads()
        async Task Rails() {
            var types = CityElements.Types.Parsers.TypeParser.GetCustomElementTypes();
            Check("the rail type exists", types.ContainsKey("rail"));
            if (!types.ContainsKey("rail")) return;
            var type = types["rail"];
            Check("the rails follow the connections and don't accept free points", type.typeData.settings.spline.FollowsConnectionsDynamically
                && !Operations.PointTargets.AcceptsGround(type));

            var created = await Call("patches.create", new {
                perimeter = new[] { Pos(-900, 900), Pos(-800, 900), Pos(-800, 1000), Pos(-900, 1100) },
                internalPoints = new[] { Pos(-850, 950) }, details = true
            });
            var railPatch = created["id"].Value<int>();
            var ids = created["points"].Select(x => x.Value<int>()).ToList();
            var internalPoint = (await Derived(railPatch))["internalPoints"][0]["id"].Value<int>();
            object On(int point) => new { terrainPoint = point };

            //placement: only on the perimeter
            await Expect("a rail point can't be free", "invalid_operation", "customElement.create",
                new { type = "rail", points = new { spline = new object[] { On(ids[0]), Pos(-700, 900) } } });
            await Expect("a rail point can't be on an internal point", "invalid_operation", "customElement.create",
                new { type = "rail", points = new { spline = new object[] { On(ids[0]), On(internalPoint) } } });
            int rail = 0;
            await CheckUndo("rail created", async () => rail = (await Call("customElement.create", new { type = "rail", name = "Rail test",
                points = new { spline = new object[] { On(ids[0]), On(ids[2]) } } })).Value<int>());
            CustomElement Rail() => History.UndoManager.GetAliveElement(rail) as CustomElement;
            List<Vector3> Centers() => Rail().splineData.sections.Select(s => s.Position).ToList();
            int RoomOf(int element) => (History.UndoManager.GetAliveElement(element) as CustomElement)?.state.State("room")?.Int("id", -1) ?? -1;
            Check("the first point makes its patch the room of the rail", RoomOf(rail) == railPatch);
            await Call("city.flush");
            Check("two points: the span goes through the perimeter point between them, the shorter way", Centers().Count == 3
                && Centers()[1].DistanceTo(new Vector3(-800, Centers()[1].Y, 900)) < 0.01f);
            await Expect("a rail point needs its target", "invalid_param", "customElement.insert", new { element = rail, array = "spline" });
            await Expect("a rail point can't be detached", "invalid_operation", "customElement.detachPoint", new { element = rail, path = "spline.0" });

            //the spans follow the perimeter when it changes between the points
            var inserted = (await Call("patches.addPerimeterPoint", new { patch = railPatch, point = new { link = new[] { ids[0], ids[1] }, position = V(-850, 0, 900) } })).Value<int>();
            await Call("city.flush");
            Check("a perimeter point inserted between the points is followed", Centers().Count == 4);
            await Call("patches.removePoint", new { patch = railPatch, point = inserted });
            await Call("city.flush");
            Check("and a perimeter point removed is not", Centers().Count == 3);
            await CheckUndo("rail moved with its patch point", () => Call("terrainPoints.move", new { point = ids[1], position = V(-790, 0, 905) }));
            await Call("city.flush");
            Check("the span follows the moved perimeter point", Centers()[1].DistanceTo(new Vector3(-790, Centers()[1].Y, 905)) < 0.01f);

            //loop and direction
            await CheckUndo("rail closed", () => Call("state.setParam", new { @ref = rail, name = "closed", value = true }));
            await Call("city.flush");
            Check("a closed rail of two points goes back the other way around", Rail().splineData.closed && Centers().Count == 5
                && Centers()[3].DistanceTo(new Vector3(-900, Centers()[3].Y, 1100)) < 0.01f);
            await Call("state.setParam", new { @ref = rail, name = "closed", value = false });
            await CheckUndo("rail reversed", () => Call("customElement.reverse", new { element = rail }));
            await Call("city.flush");
            Check("the reversed rail starts from its last point", Rail().GetLeaves()[0].leaf.point == History.UndoManager.GetAliveElement(ids[2]) as TerrainPoint);
            await CheckUndo("rail point added on the perimeter", () => Call("customElement.insert", new { element = rail, array = "spline", to = On(ids[3]) }));
            await Call("city.flush");
            Check("a point added next to the last one adds one span", Centers().Count == 4);

            //along a road: on the anchors of its side, the span follows the anchor chain
            var anchors = ((JArray)await Call("anchors.list", new { unusedBy = "terrainPatch" })).Where(a => a["of"].Value<int>() == roadA
                && !a["roadEnd"].Value<bool>() && !a["customElementsOnly"].Value<bool>()).ToList();
            JToken Next(JToken a) => a["next"].Type == JTokenType.Null ? null
                : anchors.FirstOrDefault(x => x["index"].Value<int>() == a["next"]["index"].Value<int>() && x["of"].Value<int>() == a["next"]["of"].Value<int>());
            var first = anchors.FirstOrDefault(a => Next(a) != null && Next(Next(a)) != null);
            Check("road A has a chain of three anchors", first != null);
            int sharedPatch = -1;
            List<int> sharedIds = null;
            if (first != null) {
                object Anchor(JToken a) => new { anchor = new { of = roadA, index = a["index"].Value<int>() } };
                await Expect("a rail point can't leave its room", "invalid_operation", "customElement.insert",
                    new { element = rail, array = "spline", to = Anchor(first) });
                var roadRail = (await Call("customElement.create", new { type = "rail", name = "Road rail test",
                    points = new { spline = new object[] { Anchor(first), Anchor(Next(Next(first))) } } })).Value<int>();
                await Call("city.flush");
                var element = History.UndoManager.GetAliveElement(roadRail) as CustomElement;
                Check("a road rail follows the anchors between its points", element.splineData.sections.Length >= 3 && RoomOf(roadRail) == roadA);
                var exported = await Call("elements.geometry", new { @ref = roadRail });
                Check("the export of a rail has its sections", exported["element"]?["spline"]?["sections"]?.Count() == element.splineData.sections.Length);
                await Expect("the room can't be an element the points aren't on", "invalid_value", "state.setParam",
                    new { @ref = roadRail, name = "room", value = railPatch });
                await Call("customElement.delete", new { element = roadRail });

                //a patch along the road: its points on the anchors are on the perimeters of both, the room is chosen
                var a0 = first["position"].ToObject<float[]>();
                var outside = a0[2] > 0 ? 60 : -60;
                var sharedCreated = await Call("patches.create", new { perimeter = new object[] { Anchor(first), Anchor(Next(Next(first))),
                    Pos(a0[0], a0[2] + outside) }, details = true });
                sharedPatch = sharedCreated["id"].Value<int>();
                sharedIds = sharedCreated["points"].Select(x => x.Value<int>()).ToList();
                await Expect("a rail from a point on two rooms needs its room", "invalid_param", "customElement.create",
                    new { type = "rail", points = new { spline = new object[] { On(sharedIds[0]), On(sharedIds[1]) } } });
                var patchSide = (await Call("customElement.create", new { type = "rail", state = new { room = sharedPatch },
                    points = new { spline = new object[] { On(sharedIds[0]), On(sharedIds[1]) } } })).Value<int>();
                var roadSide = (await Call("customElement.create", new { type = "rail", state = new { room = roadA },
                    points = new { spline = new object[] { On(sharedIds[0]), On(sharedIds[1]) } } })).Value<int>();
                await Call("city.flush");
                int Sections(int id) => (History.UndoManager.GetAliveElement(id) as CustomElement).splineData.sections.Length;
                Check("in the patch the span is its edge, along the road it follows the anchors", Sections(patchSide) == 2 && Sections(roadSide) == 3);
                await Call("customElement.delete", new { element = patchSide });
                await Call("customElement.delete", new { element = roadSide });
            }
            //the click modes: only what the type accepts is shown and placed, the first point closes the loop
            TerrainPoint PointOf(int point) => History.UndoManager.GetAliveElement(point) as TerrainPoint;
            var placer = builder.customElementPlacer;
            void Click(Node3D obj, Vector3 position, string label) =>
                History.UndoManager.Record(label, () => placer.PlaceAt(new GameEngine.Raycast.RaycastHit { collider = obj, point = position }));
            History.UndoManager.Record("start rail placement", () => CallBuilder<object>("StartCustomElementCreation", "rail", "CREATE_CUSTOM_ELEMENT"));
            await Frames(1);
            Check("rail placement shows the perimeter points, not the internal ones", PointOf(ids[1]).GetObject().IsVisibleInTree()
                && !PointOf(internalPoint).GetObject().IsVisibleInTree());
            Click(null, new Vector3(-850, 0, 950), "rail on the ground");
            Check("a click on the ground doesn't create a rail", placer.GetElement() == null);
            //the handle under the mouse: not on a segment the type refuses (a new point part way along an edge)
            var handleField = typeof(CityBuilderMenuBar).Assembly.GetType("ActionHandlerManager")
                .GetField("handle", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
            bool HandleShownFor(GameEngine.Raycast.RaycastHit? hit, int index) {
                if (handleField.GetValue(null) is Node3D shown) GameEngine.GameObject.SetEnabled(shown, false);
                var hits = new List<GameEngine.Raycast.RaycastHit?> { null, null, null };
                hits[index] = hit;
                placer.ShowOnMap(hits);
                return handleField.GetValue(null) is Node3D h && GameEngine.GameObject.GetEnabled(h);
            }
            var segment = GameEngine.Scriptable.FindMultipleRecursive<PointLink>(PointOf(ids[0]).GetObject()).FirstOrDefault();
            Check("the patch has a segment from its first point", segment != null);
            if (segment != null) {
                Check("no handle on a segment the rail refuses", !HandleShownFor(new GameEngine.Raycast.RaycastHit { collider = segment,
                    point = PointOf(ids[0]).GetPoint() }, 1));
            }
            Check("a handle on a perimeter point", HandleShownFor(new GameEngine.Raycast.RaycastHit { collider = PointOf(ids[1]).GetObject(),
                point = PointOf(ids[1]).GetPoint() }, 0));
            Click(PointOf(ids[1]).GetObject(), PointOf(ids[1]).GetPoint(), "first rail point");
            var placed = placer.GetElement();
            Check("a click on a perimeter point creates a rail", placed?.TypeName == "rail" && placed.GetAllPoints().Count == 1);
            if (placed != null && sharedIds != null) {
                Check("then only the points of its room are shown", PointOf(ids[2]).GetObject().IsVisibleInTree()
                    && !PointOf(sharedIds[0]).GetObject().IsVisibleInTree());
                Click(PointOf(sharedIds[0]).GetObject(), PointOf(sharedIds[0]).GetPoint(), "rail point on another room");
                Check("a click on another room adds no point", placed.GetAllPoints().Count == 1);
            }
            if (placed != null) {
                Click(null, new Vector3(-850, 0, 950), "rail point on the ground");
                Check("a click on the ground adds no point", placed.GetAllPoints().Count == 1);
                Click(PointOf(ids[3]).GetObject(), PointOf(ids[3]).GetPoint(), "second rail point");
                Check("a click on another perimeter point adds it", placed.GetAllPoints().Count == 2);
                Click(PointOf(ids[1]).GetObject(), PointOf(ids[1]).GetPoint(), "close the rail");
                Check("a click on the first point closes the rail", placed.state.Bool("closed")
                    && placer.placementMode == ElementPlacer.CustomElementPlacer.PlacementMode.None);
                await Call("customElement.delete", new { element = History.ElementRegistry.GetId(placed) });
            }
            builder.CloseAllPanels();

            //a first click on a point of two rooms: the user chooses the room
            if (sharedIds != null) {
                History.UndoManager.Record("start rail placement", () => CallBuilder<object>("StartCustomElementCreation", "rail", "CREATE_CUSTOM_ELEMENT"));
                await Frames(1);
                Click(PointOf(sharedIds[0]).GetObject(), PointOf(sharedIds[0]).GetPoint(), "first rail point on two rooms");
                var choices = placer.ownerChoices;
                Check("a click on a point of two rooms asks which one", placer.GetElement() == null && choices?.Count == 2
                    && choices.Contains(History.UndoManager.GetAliveElement(roadA)) && choices.Contains(History.UndoManager.GetAliveElement(sharedPatch)));
                if (choices?.Count == 2) {
                    placer.ChooseOwner(choices.IndexOf(History.UndoManager.GetAliveElement(roadA)));
                    var chosen = placer.GetElement();
                    Check("the rail is created in the room chosen", chosen != null && chosen.GetAllPoints().Count == 1
                        && RoomOf(History.ElementRegistry.GetId(chosen)) == roadA && placer.ownerChoices == null);
                    if (chosen != null) {
                        await CheckUndo("rail in the chosen room", () => Call("customElement.delete", new { element = History.ElementRegistry.GetId(chosen) }));
                    }
                }
                placer.CloseOwnerMenu();
                builder.CloseAllPanels();
                await Call("patches.delete", new { patch = sharedPatch });
            }

            await Call("customElement.delete", new { element = rail });
            await Call("patches.delete", new { patch = railPatch });
        }
    }
}
