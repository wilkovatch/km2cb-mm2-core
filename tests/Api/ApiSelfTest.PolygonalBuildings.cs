using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using Newtonsoft.Json.Linq;

namespace Api {
    public partial class ApiSelfTest {
        //The polygonal buildings: the closed outline through their points (also concave), the walls always facing outwards
        //whichever way the points go around, the roof, the points inserted in an edge, the shared and individual sides of
        //the walls, undo, the copy of their properties, the group transform, saving and loading
        async Task PolygonalBuildings() {
            T Element<T>(int id) where T : class => History.UndoManager.GetAliveElement(id) as T;
            async Task<JToken> Derived(int id) => (await Call("elements.get", new { @ref = id, derived = true }))["derived"];
            //even-odd test on the horizontal plane
            bool Inside(List<Vector3> outline, Vector3 p) {
                var res = false;
                for (int i = 0, j = outline.Count - 1; i < outline.Count; j = i++) {
                    var a = outline[i];
                    var b = outline[j];
                    if ((a.Z > p.Z) != (b.Z > p.Z) && p.X < (b.X - a.X) * (p.Z - a.Z) / (b.Z - a.Z) + a.X) res = !res;
                }
                return res;
            }
            //every facade has the outside in front of it and the inside behind it
            bool FacingOutwards(PolygonalBuilding b) {
                var outline = b.GetPointsComponents().Select(p => p.GetPoint()).ToList();
                foreach (var wall in b.walls) {
                    if (wall.front == null || wall.front.facades.Count == 0) return false;
                    var mid = (wall.firstPoint.GetPoint() + wall.lastPoint.GetPoint()) * 0.5f;
                    var facing = wall.front.facades[0].forward;
                    if (Inside(outline, mid + facing * 0.5f) || !Inside(outline, mid - facing * 0.5f)) return false;
                }
                return true;
            }
            float RoofArea(PolygonalBuilding b) {
                var roof = b.roof?.GetSubmesh();
                if (roof == null || roof.Value.indices == null) return 0;
                var v = roof.Value.vertices;
                var res = 0.0f;
                foreach (var indices in roof.Value.indices) {
                    for (int t = 0; t + 2 < indices.Length; t += 3) {
                        var a = v[indices[t]];
                        var c1 = v[indices[t + 1]] - a;
                        var c2 = v[indices[t + 2]] - a;
                        res += Mathf.Abs(c1.X * c2.Z - c1.Z * c2.X) * 0.5f;
                    }
                }
                return res;
            }

            //an L: 30 x 25 without a 15 x 15 corner, 525 m²
            var lShape = new[] { (0f, 600f), (30f, 600f), (30f, 610f), (15f, 610f), (15f, 625f), (0f, 625f) };
            var created = await Call("polygonalBuildings.create", new { points = lShape.Select(p => Pos(p.Item1, p.Item2)).ToArray(), details = true });
            var building = created["id"].Value<int>();
            var d = await Derived(building);
            Check("a concave outline has a wall for each edge", Len(d["walls"]) == 6 && !d["selfIntersecting"].Value<bool>());
            var element = Element<PolygonalBuilding>(building);
            Check("the facades of a concave building face outwards", FacingOutwards(element));
            Check("the roof covers the concave outline", Mathf.Abs(RoofArea(element) - 525) < 0.5f);
            var maxY = element.GetPointsComponents().Max(p => p.GetPoint().Y);
            var roofVertices = element.roof?.GetSubmesh().vertices;
            Check("the roof is flat, at the height above the highest point", roofVertices != null && roofVertices.Length >= 6
                && roofVertices.All(v => Mathf.Abs(v.Y - (maxY + element.state.Float("height"))) < 0.01f));
            var reversed = (await Call("polygonalBuildings.create", new { points = lShape.Reverse().Select(p => Pos(p.Item1 + 100, p.Item2)).ToArray() })).Value<int>();
            Check("the facades face outwards whichever way the points go around", FacingOutwards(Element<PolygonalBuilding>(reversed)));
            await Call("polygonalBuildings.delete", new { building = reversed });
            var crossing = (await Call("polygonalBuildings.create", new { points = new[] { Pos(200, 600), Pos(220, 620), Pos(220, 600), Pos(200, 620) } })).Value<int>();
            Check("a crossing outline is still generated, and reported", Len((await Derived(crossing))["walls"]) == 4 && (await Derived(crossing))["selfIntersecting"].Value<bool>());
            await Call("polygonalBuildings.delete", new { building = crossing });
            await Expect("a polygonal building needs three points", "invalid_value", "polygonalBuildings.create", new { points = new[] { Pos(0, 700), Pos(10, 700) } });

            //one side for every wall: an edit of any wall is an edit of all of them
            int Floors(Building wall) => wall.front.state.Array<ObjectState>("upperFloors")?.Length ?? 0;
            var floors = Floors(element.walls[0]);
            await CheckUndo("shared side floor added", () => Call("sides.addFloor", new { side = new { polygon = building, wall = 1 } }));
            await Frames(2);
            Check("a floor added to the shared side is on every wall", element.walls.All(w => Floors(w) == floors + 1)
                && element.state.State("sideState").Array<ObjectState>("upperFloors").Length == floors + 1);

            //one side for each wall
            await CheckUndo("individual sides", () => Call("polygonalBuildings.setIndividualSides", new { building, individual = true }));
            await CheckUndo("individual side floor added", () => Call("sides.addFloor", new { side = new { polygon = building, wall = 1 } }));
            await Frames(2);
            Building WallOf(int index) => element.walls.Find(w => w.firstPoint == element.GetPointsComponents()[index]);
            Check("a floor added to the side of one wall is only on that wall", Floors(WallOf(1)) == floors + 2
                && element.walls.Where(w => w != WallOf(1)).All(w => Floors(w) == floors + 1));

            //a point inserted in an edge splits its wall, both parts keep its side
            var inserted = 0;
            await CheckUndo("polygonal building point inserted", async () => inserted = (await Call("polygonalBuildings.insertPoint", new { building, position = V(30, 0, 604), onGround = true })).Value<int>());
            await Frames(2);
            var order = element.GetPointsComponents();
            Check("the point is inserted in the closest edge", order.Count == 7 && History.ElementRegistry.GetId(order[2]) == inserted && element.walls.Count == 7);
            Check("the new wall gets a copy of the side of the wall it split", Floors(WallOf(1)) == floors + 2 && Floors(WallOf(2)) == floors + 2
                && WallOf(1).front.state != WallOf(2).front.state);
            Check("the facades still face outwards", FacingOutwards(element));
            var data = (await Call("elements.get", new { @ref = building }))["data"];
            Check("the sides of the walls are saved by point", Len(data["wallStates"]) == 7 && data["wallStates"].All(s => s.Type == JTokenType.Object));

            await PolygonalBuildingEditor(element);

            //the walls are not buildings to the user: the properties are copied between polygonal buildings
            var other = (await Call("polygonalBuildings.create", new { points = new[] { Pos(100, 600), Pos(120, 600), Pos(110, 620) } })).Value<int>();
            await Call("state.setBuiltin", new { @ref = building, name = "height", value = 31 });
            await CheckUndo("polygonal building properties copied", () => Call("elements.copyProperties", new { from = building, to = new[] { other } }));
            Check("the copy has the height and the individual sides", Mathf.Abs(Element<PolygonalBuilding>(other).state.Float("height") - 31) < 0.001f
                && Element<PolygonalBuilding>(other).IsIndividual());
            await CheckUndo("polygonal building moved", () => Call("elements.transform", new { elements = new[] { other }, offset = V(10, 0, 0) }));
            Check("the points of the polygonal building moved", Mathf.Abs(Element<PolygonalBuilding>(other).GetPointsComponents()[0].GetPoint().X - 110) < 0.01f);
            var geometry = await Call("elements.geometry", new { @ref = building });
            Check("the geometry has the walls with their points and the roof", Len(geometry["element"]["wallPoints"]) == 7 && Len(geometry["element"]["walls"]) == 7
                && geometry["element"]["roof"].Type == JTokenType.Object);
            await CheckUndo("polygonal building deleted", () => Call("polygonalBuildings.delete", new { building = other }));
            Check("the polygonal building is deleted", Element<PolygonalBuilding>(other) == null);

            //saved and loaded again
            await Call("city.save");
            await Call("city.load", new { folder });
            var loaded = (JArray)await Call("elements.list", new { kind = "polygonalBuilding" });
            var reloaded = loaded.Count == 1 ? Element<PolygonalBuilding>(loaded[0]["id"].Value<int>()) : null;
            Check("the polygonal building is loaded with its sides", reloaded != null && reloaded.IsIndividual() && reloaded.walls.Count == 7
                && reloaded.GetWallStatesArray().Count(s => s != null) == 7 && FacingOutwards(reloaded));
        }

        //the editor: the Buildings submenu of the Create menu, the handle of the roof setting the height, and the list of the
        //walls, usable only with individual sides (the building has them when this starts)
        async Task PolygonalBuildingEditor(PolygonalBuilding element) {
            var flags = System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance;
            var building = History.ElementRegistry.GetId(element);

            //the Create menu
            builder.ReloadCreateMenu();
            var createMenu = CallBuilder<MenuBar>("GetMenuBar").FindChildren("*", nameof(MenuButton), true, false).OfType<MenuButton>()
                .First(b => b.Text == StringManager.Get("CREATE")).GetPopup();
            var index = Enumerable.Range(0, createMenu.ItemCount).FirstOrDefault(i => createMenu.GetItemSubmenuNode(i) != null
                && createMenu.GetItemText(i) == StringManager.Get("CREATE_BUILDINGS_SUBMENU"), -1);
            var inner = index >= 0 ? createMenu.GetItemSubmenuNode(index) : null;
            string Text(string key) => StringManager.Get(key).Split('	')[0]; //the shortcut is shown apart
            Check("the building lines and the polygonal buildings are in the Buildings submenu of the Create menu", inner != null && inner.ItemCount == 2
                && inner.GetItemText(0) == Text("CREATE_BUILDING_LINE") && inner.GetItemText(1) == Text("CREATE_POLYGONAL_BUILDING")
                && !Enumerable.Range(0, createMenu.ItemCount).Any(i => createMenu.GetItemText(i) == Text("CREATE_BUILDING_LINE")));

            //the editor
            var panel = (EditorPanels.Buildings.PolygonalBuildingEditorPanel)typeof(CityBuilderMenuBar).GetField("polygonalBuildingEditorPanel", flags).GetValue(builder);
            History.UndoManager.Record("edit", () => builder.SelectObject(element, true, null));
            await Frames(3);
            Check("a click on the building opens its editor", panel.ActiveSelf() && panel.GetBuilding() == element);

            //the handle of the roof
            StaticBody3D SizeHandle(string name) => M.GetChildren().OfType<StaticBody3D>().FirstOrDefault(h => h.Name == name && h.ProcessMode != Node.ProcessModeEnum.Disabled);
            var heightHandle = SizeHandle("BuildingHeightHandle");
            var maxY = element.GetPointsComponents().Max(p => p.GetPoint().Y);
            var height = element.state.Float("height");
            Check("the roof of the edited building has a handle at its height, and there is no depth handle", heightHandle != null && SizeHandle("BuildingDepthHandle") == null
                && Mathf.Abs(GameEngine.GameObject.GetPosition(heightHandle).Y - (maxY + height)) < 0.01f);
            if (heightHandle != null) {
                var gizmo = builder.gizmo;
                var startDrag = gizmo.GetType().GetMethod("StartTransform", flags);
                var finishDrag = gizmo.GetType().GetMethod("FinishTransform", flags);
                gizmo.ClearTargets();
                gizmo.AddTarget(heightHandle);
                await Frames(2);
                Check("the gizmo moves the roof only up and down", gizmo.posAxesAllowed.SequenceEqual(new[] { false, true, false })
                    && !gizmo.rotAxesAllowed.Any(a => a) && gizmo.space == RuntimeGizmos.TransformSpace.Local);
                Godot.Input.ActionPress("Select");
                startDrag.Invoke(gizmo, new object[] { RuntimeGizmos.TransformType.Move });
                GameEngine.GameObject.SetPosition(heightHandle, GameEngine.GameObject.GetPosition(heightHandle) + new Vector3(2, 6, 0));
                gizmo.onAnyChange?.Invoke();
                await Frames(2);
                finishDrag.Invoke(gizmo, null);
                Godot.Input.ActionRelease("Select");
                await Frames(3);
                Check("moving the roof handle sets the height", Mathf.Abs(element.state.Float("height") - (height + 6)) < 0.01f
                    && Mathf.Abs(element.roof.GetSubmesh().vertices[0].Y - (maxY + height + 6)) < 0.01f);
                await Call("history.undo");
                await Frames(2);
                Check("the drag of the roof handle is an undo step", Mathf.Abs(element.state.Float("height") - height) < 0.01f);
                gizmo.ClearTargets();
            }

            //the list of the walls
            var wallList = (EditorPanelElements.ScrollList)typeof(EditorPanels.Buildings.PolygonalBuildingEditorPanel).GetField("wallList", flags).GetValue(panel);
            panel.Update();
            Check("with individual sides the list of the walls can be used", wallList.GetInteractable());
            await Call("polygonalBuildings.setIndividualSides", new { building, individual = false });
            await Frames(2);
            panel.Update();
            wallList.SetValue(1);
            Check("without individual sides it can't, and nothing in it can be selected", !wallList.GetInteractable() && wallList.Selected == -1);
            await Call("polygonalBuildings.setIndividualSides", new { building, individual = true });
            await Frames(2);
            History.UndoManager.Record("close", () => CallBuilder<object>("DeselectAndCloseCurrentPanel"));
            await Frames(2);
            Check("the roof handle is hidden with the editor", SizeHandle("BuildingHeightHandle") == null);
        }
    }
}
