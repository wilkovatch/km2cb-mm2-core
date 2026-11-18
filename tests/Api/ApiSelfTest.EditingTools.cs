using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Godot;
using Newtonsoft.Json.Linq;
using GO = GameEngine.GameObject;

namespace Api {
    public partial class ApiSelfTest {
        //The tools editing several elements and reshaping terrain patches and building lines: the group transform and the
        //multiple selection, the property copy and its eyedropper, the points inserted in a segment, splitting and merging
        //patches and lines, and the size handles of the buildings. First through the API, then through the editor
        async Task EditingTools() {
            var flags = System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
            TerrainPoint PointOf(int id) => History.UndoManager.GetAliveElement(id) as TerrainPoint;
            T Element<T>(int id) where T : class => History.UndoManager.GetAliveElement(id) as T;
            bool Near(Vector3 a, float x, float z) => Mathf.Abs(a.X - x) < 0.01f && Mathf.Abs(a.Z - z) < 0.01f;
            async Task<List<int>> Perimeter(int patch) => (await Call("elements.get", new { @ref = patch }))["data"]["perimeterPointsIds"].Select(x => x.Value<int>()).ToList();
            async Task<JToken> Line(int line) => (await Call("elements.get", new { @ref = line }))["data"];
            async Task<List<int>> LinePoints(int line) => (await Line(line))["linePoints"].Select(x => x.Value<int>()).ToList();

            // Terrain patches
            var created = await Call("patches.create", new { perimeter = new[] { Pos(0, 0), Pos(100, 0), Pos(100, 100), Pos(0, 100) }, internalPoints = new[] { Pos(80, 60) }, details = true });
            var patch = created["id"].Value<int>();
            var p = created["points"].Select(x => x.Value<int>()).ToList();
            var inserted = 0;
            await CheckUndo("perimeter point inserted", async () => inserted = (await Call("patches.insertPerimeterPoint", new { patch, position = V(50, 0, -20), onGround = true })).Value<int>());
            Check("the point is inserted in the closest segment", (await Perimeter(patch)).SequenceEqual(new[] { p[0], inserted, p[1], p[2], p[3] }));
            Check("the inserted point is free", GO.IsNull(PointOf(inserted).anchor));
            //the point on a link keeps following it, and goes between its two points (also on the last segment)
            var followed = (await Call("patches.addPerimeterPoint", new { patch, point = new { link = new[] { p[2], p[3] }, position = V(50, 0, 100) } })).Value<int>();
            Check("a point on the last segment goes between its points, following it", (await Perimeter(patch)).SequenceEqual(new[] { p[0], inserted, p[1], p[2], followed, p[3] })
                && PointOf(followed).anchor is LineAnchor);
            await Call("patches.removePoint", new { patch, point = followed });
            await Expect("a patch can't be split between two points next to each other", "invalid_operation", "patches.split", new { patch, from = p[0], to = inserted });
            var half = 0;
            await CheckUndo("patch split", async () => half = (await Call("patches.split", new { patch, from = p[1], to = p[3] })).Value<int>());
            Check("the patch keeps the perimeter from the second point to the first", (await Perimeter(patch)).SequenceEqual(new[] { p[3], p[0], inserted, p[1] }));
            Check("the new patch gets the rest, sharing the two points", (await Perimeter(half)).SequenceEqual(new[] { p[1], p[2], p[3] })
                && PointOf(p[1]).GetLinks().Count == 2 && PointOf(p[3]).GetLinks().Count == 2);
            Check("the internal point goes to the patch it is in", Element<TerrainPatch>(half).GetInternalPointsComponents().Count == 1
                && Element<TerrainPatch>(patch).GetInternalPointsComponents().Count == 0);
            await CheckUndo("patches merged", () => Call("patches.merge", new { patch, other = half }));
            Check("the merged patch has the points of both", (await Perimeter(patch)).OrderBy(x => x).SequenceEqual(new[] { p[0], p[1], p[2], p[3], inserted }.OrderBy(x => x))
                && Element<TerrainPatch>(half) == null && Element<TerrainPatch>(patch).GetInternalPointsComponents().Count == 1);
            var left = (await Call("patches.create", new { perimeter = new[] { Pos(200, 0), Pos(250, 0), Pos(250, 50), Pos(200, 50) } })).Value<int>();
            var right = (await Call("patches.create", new { perimeter = new[] { Pos(250, 0), Pos(300, 0), Pos(300, 50), Pos(250, 50) } })).Value<int>();
            await CheckUndo("patches with a side at the same positions merged", () => Call("patches.merge", new { patch = left, other = right }));
            Check("the side shared by position is removed", (await Perimeter(left)).Count == 6);
            var far = (await Call("patches.create", new { perimeter = new[] { Pos(400, 0), Pos(450, 0), Pos(450, 50) } })).Value<int>();
            await Expect("patches without a shared side can't be merged", "invalid_operation", "patches.merge", new { patch = left, other = far });

            // Building lines
            var lineInfo = await Call("lines.create", new { points = new[] { Pos(0, 200), Pos(50, 200), Pos(100, 200), Pos(150, 200) }, dividing = new[] { 1, 2 }, details = true });
            var line = lineInfo["id"].Value<int>();
            var lp = lineInfo["points"].Select(x => x.Value<int>()).ToList();
            await Call("state.setBuiltin", new { @ref = new { line, building = 2 }, name = "height", value = 33 });
            var mid = 0;
            await CheckUndo("line point inserted", async () => mid = (await Call("lines.insertPoint", new { line, position = V(75, 0, 190), onGround = true })).Value<int>());
            Check("the line point is inserted in the closest segment, in the same building", (await LinePoints(line)).SequenceEqual(new[] { lp[0], lp[1], mid, lp[2], lp[3] })
                && Len((await Line(line))["buildings"]) == 3);
            Check("the segments of a line have links, but not its last point", GameEngine.Scriptable.FindMultipleRecursive<PointLink>(PointOf(lp[0]).GetObject()).Count() == 1
                && GameEngine.Scriptable.FindMultipleRecursive<PointLink>(PointOf(lp[3]).GetObject()).Count() == 0);
            await Expect("a line can't be split at an end", "invalid_operation", "lines.split", new { line, point = lp[0] });
            var tail = 0;
            await CheckUndo("line split", async () => tail = (await Call("lines.split", new { line, point = lp[2] })).Value<int>());
            Check("the line keeps the points up to the split, the new line gets the rest", (await LinePoints(line)).SequenceEqual(new[] { lp[0], lp[1], mid, lp[2] })
                && (await LinePoints(tail)).SequenceEqual(new[] { lp[2], lp[3] }));
            Check("the buildings keep their properties", Element<BuildingLine>(line).buildings.Count == 2 && Element<BuildingLine>(tail).buildings.Count == 1
                && Mathf.Abs(Element<BuildingLine>(tail).buildings[0].state.Float("height") - 33) < 0.001f);
            await CheckUndo("lines joined", () => Call("lines.merge", new { line, other = tail }));
            Check("the joined line has the points in order and the three buildings", (await LinePoints(line)).SequenceEqual(new[] { lp[0], lp[1], mid, lp[2], lp[3] })
                && Element<BuildingLine>(line).buildings.Count == 3 && Mathf.Abs(Element<BuildingLine>(line).buildings[2].state.Float("height") - 33) < 0.001f);
            var apart = (await Call("lines.create", new { points = new[] { Pos(250, 200), Pos(200, 200) } })).Value<int>();
            await CheckUndo("lines apart joined", () => Call("lines.merge", new { line, other = apart }));
            var joined = Element<BuildingLine>(line).GetPointsComponents();
            Check("the closest ends are joined with a building between them, reversing the other line", joined.Count == 7 && Element<BuildingLine>(line).buildings.Count == 5
                && Near(joined[5].GetPoint(), 200, 200) && Near(joined[6].GetPoint(), 250, 200));

            // Group transform
            var road = (await Call("roads.create", new { points = new[] { Pos(0, -200), Pos(100, -200) } })).Value<int>();
            var road2 = (await Call("roads.create", new { points = new object[] { new { roadEnd = new { road, end = "end" } }, Pos(200, -200) } })).Value<int>();
            var junction = Api.CityApi.IdOf(Element<Road>(road).endIntersection);
            var corner = await Call("patches.create", new { perimeter = new[] { Pos(0, -300), Pos(40, -300), Pos(40, -260) }, details = true });
            var cornerPatch = corner["id"].Value<int>();
            var cp = corner["points"].Select(x => x.Value<int>()).ToList();
            await CheckUndo("group moved", () => Call("elements.transform", new { elements = new[] { road, cornerPatch }, offset = V(10, 0, 5) }));
            Check("the points of the patch and the free end of the road moved", Near(PointOf(cp[0]).GetPoint(), 10, -295) && Near(GO.GetPosition(Element<Road>(road).points[0]), 10, -195));
            Check("the end of the road on an intersection that is not in the group stayed", Near(GO.GetPosition(Element<Road>(road).points[1]), 100, -200));
            await CheckUndo("group with an intersection moved", () => Call("elements.transform", new { elements = new[] { junction }, offset = V(0, 0, -10) }));
            Check("an intersection moves the ends of its roads", Near(GO.GetPosition(Element<Road>(road).points[1]), 100, -210) && Near(GO.GetPosition(Element<Road>(road2).points[0]), 100, -210));
            await CheckUndo("group rotated", () => Call("elements.transform", new { elements = new[] { cornerPatch }, rotation = 90, pivot = V(10, 0, -295) }));
            Check("the rotation is around the pivot, to the right", Near(PointOf(cp[0]).GetPoint(), 10, -295) && Near(PointOf(cp[1]).GetPoint(), 10, -335));
            await CheckUndo("group scaled", () => Call("elements.transform", new { elements = new[] { cornerPatch }, scale = V(2, 2, 2), pivot = V(10, 0, -295) }));
            Check("the scale is from the pivot", Near(PointOf(cp[1]).GetPoint(), 10, -375));
            await Expect("a terrain point is not an element to transform", "invalid_operation", "elements.transform", new { elements = new[] { cp[0] }, offset = V(1, 0, 0) });

            // Property copy
            var source = (await Call("patches.create", new { perimeter = new[] { Pos(500, 0), Pos(550, 0), Pos(550, 50) } })).Value<int>();
            var target = (await Call("patches.create", new { perimeter = new[] { Pos(600, 0), Pos(650, 0), Pos(650, 50) } })).Value<int>();
            await Call("state.setBuiltin", new { @ref = source, name = "smooth", value = 3 });
            await Call("state.setBuiltin", new { @ref = target, name = "projectToGround", value = false });
            await CheckUndo("properties copied", () => Call("elements.copyProperties", new { from = source, to = new[] { target, far } }));
            Check("the properties are copied, but not where the points are", Element<TerrainPatch>(target).state.Int("smooth") == 3 && Element<TerrainPatch>(far).state.Int("smooth") == 3
                && !Element<TerrainPatch>(target).state.Bool("projectToGround"));
            await Expect("the properties of another kind of element can't be copied", "wrong_kind", "elements.copyProperties", new { from = source, to = new[] { road } });
            await CheckUndo("building properties copied", () => Call("elements.copyProperties", new { from = new { line, building = 2 }, to = new object[] { new { line, building = 0 } } }));
            Check("a building gets the properties of another one", Mathf.Abs(Element<BuildingLine>(line).buildings[0].state.Float("height") - 33) < 0.001f);

            // The editor
            void CloseAlert() {
                var alert = typeof(CityBuilderMenuBar).GetField("alert", flags).GetValue(builder);
                if (alert != null && builder.AlertActive()) alert.GetType().GetMethod("Close", flags).Invoke(alert, null);
            }
            IEnumerable<EditorPanelElement> Elements(EditorPanel panel) {
                var pages = (System.Collections.IList)typeof(EditorPanel).GetField("pages", flags).GetValue(panel);
                return pages.Cast<EditorPanelPage>().SelectMany(page => ((List<List<EditorPanelElement>>)typeof(EditorPanelPage).GetField("elements", flags).GetValue(page)).SelectMany(row => row));
            }
            Godot.Button ButtonOf(EditorPanel panel, string key) => Elements(panel).OfType<EditorPanelElements.Button>()
                .Select(b => (Godot.Button)typeof(EditorPanelElements.Button).GetField("button", flags).GetValue(b)).FirstOrDefault(b => b.Text == StringManager.Get(key));
            EditorPanel Shown() => CallBuilder<EditorPanel>("GetActivePanel");
            T PanelOf<T>(string field) => (T)typeof(CityBuilderMenuBar).GetField(field, flags).GetValue(builder);
            async Task Press(EditorPanel panel, string key) {
                ButtonOf(panel, key).EmitSignal(Godot.Button.SignalName.Pressed);
                await Frames(2);
            }
            async Task Edit(object element) {
                History.UndoManager.Record("edit", () => builder.SelectObject(element is Intersection i ? i.geo : (Node3D)element, true, null));
                await Frames(2);
            }
            async Task Close() {
                History.UndoManager.Record("close", () => CallBuilder<object>("DeselectAndCloseCurrentPanel"));
                await Frames(2);
            }
            var gizmo = builder.gizmo;
            var startDrag = gizmo.GetType().GetMethod("StartTransform", flags);
            var finishDrag = gizmo.GetType().GetMethod("FinishTransform", flags);
            //a drag of the gizmo on its target: the target is moved as the gizmo does, and the listeners are told
            async Task Drag(Node3D node, System.Action move) {
                gizmo.ClearTargets();
                gizmo.AddTarget(node);
                Godot.Input.ActionPress("Select");
                startDrag.Invoke(gizmo, new object[] { RuntimeGizmos.TransformType.Move });
                move();
                gizmo.onAnyChange?.Invoke();
                await Frames(2);
                finishDrag.Invoke(gizmo, null);
                Godot.Input.ActionRelease("Select");
                await Frames(2);
            }

            //a click on a segment of the patch being edited inserts a free point in it
            var patchPanel = PanelOf<EditorPanels.TerrainPatchEditorPanel>("terrainPatchEditorPanel");
            await Edit(Element<TerrainPatch>(source));
            var sourcePoints = Element<TerrainPatch>(source).GetPerimeterPointsComponents();
            var segment = GameEngine.Scriptable.FindMultipleRecursive<PointLink>(sourcePoints[1].GetObject()).First(l => l.next == sourcePoints[2].GetObject());
            History.UndoManager.Record("click", () => Operations.TerrainPatches.InsertOnClickedSegment(Element<TerrainPatch>(source), segment, new Vector3(552, 0, 25)));
            M.FlagAsChanged(); await Frames(2);
            var withCorner = Element<TerrainPatch>(source).GetPerimeterPointsComponents();
            Check("a click on a segment of the edited patch inserts a free point on it", withCorner.Count == 4 && GO.IsNull(withCorner[2].anchor) && Near(withCorner[2].GetPoint(), 550, 25));
            Check("a click elsewhere is not an insertion", Operations.TerrainPatches.InsertOnClickedSegment(Element<TerrainPatch>(source), null, Vector3.Zero) == null);
            //Split: the two places of the perimeter clicked next, points or positions on its sides
            Check("the patch editor has the split and merge buttons", Shown() == patchPanel && ButtonOf(patchPanel, "TP_SPLIT") != null && ButtonOf(patchPanel, "TP_MERGE") != null);
            var patchCount = M.patches.Count;
            var outlinePicker = builder.outlinePicker;
            await Press(patchPanel, "TP_SPLIT");
            Check("the split button starts a pick of two places of the perimeter over the editor", outlinePicker.IsActive() && Shown() == patchPanel);
            var onPoint = outlinePicker.PlaceNear(withCorner[0].GetPoint());
            var onSide = outlinePicker.PlaceNear((withCorner[1].GetPoint() + withCorner[2].GetPoint()) * 0.5f);
            Check("a place near a point is that point, one on a side is a position on it", onPoint?.point == withCorner[0] && onSide != null && onSide.point == null && onSide.segment == 1);
            Check("a first place is accepted", outlinePicker.Pick(onPoint) && outlinePicker.IsActive() && M.patches.Count == patchCount);
            Check("a second place next to it is not", !outlinePicker.Pick(outlinePicker.PlaceNear(withCorner[1].GetPoint()))
                && !outlinePicker.Pick(outlinePicker.PlaceNear((withCorner[0].GetPoint() + withCorner[1].GetPoint()) * 0.5f)));
            Check("one with points between them on both sides is", outlinePicker.Pick(onSide) && !outlinePicker.IsActive());
            M.ProcessUpdate(); await Frames(2);
            var cut = Element<TerrainPatch>(source).GetPerimeterPointsComponents();
            var splitOff = M.patches[M.patches.Count - 1];
            Check("the patch is split between the two places, with a point inserted on the side", M.patches.Count == patchCount + 1 && Shown() == patchPanel
                && cut.Count == 4 && cut[3] == withCorner[0] && GO.IsNull(cut[0].anchor) && Near(cut[0].GetPoint(), onSide.position.X, onSide.position.Z)
                && splitOff.GetPerimeterPointCount() == 3 && splitOff.GetPerimeterPointsComponents().Contains(cut[0]));
            //Merge with...: the next click on a patch sharing a side, outlined in green under the mouse
            await Press(patchPanel, "TP_MERGE");
            Check("the merge button starts a pick over the editor of the patch", builder.elementPicker.IsActive() && Shown() == patchPanel && patchPanel.GetPatch() == Element<TerrainPatch>(source)
                && ListHighlight.suspended);
            //what is picked along a line across the side the two patches share: one patch, then the other, never the
            //points or the links of the edited patch on that side
            {
                Vector3 Center(TerrainPatch tp) { var c = Vector3.Zero; foreach (var q in tp.GetPerimeterPointsComponents()) c += q.GetPoint(); return c / tp.GetPerimeterPointCount(); }
                var from = Center(Element<TerrainPatch>(source));
                var to = Center(splitOff);
                await Call("view.camera.set", new { position = new[] { (from.X + to.X) / 2 - 30, 120f, (from.Z + to.Z) / 2 - 120 }, target = new[] { (from.X + to.X) / 2, 0f, (from.Z + to.Z) / 2 } });
                await Frames(3);
                var eye = GameEngine.Vector3.EncodePosition(builder.GetViewport().GetCamera3D().GlobalPosition);
                var elementOf = builder.elementPicker.GetType().GetMethod("ElementOf", flags);
                var picked = new List<object>();
                for (int k = 0; k <= 20; k++) {
                    var direction = (from.Lerp(to, k / 20.0f) - eye).Normalized();
                    picked.Add(builder.elementPicker.Raycast(gizmo, eye, direction, out var pickHit, 100000, builder.elementPicker.GetLayerMasks()[0])
                        ? elementOf.Invoke(builder.elementPicker, new object[] { pickHit }) : null);
                }
                var switchAt = picked.IndexOf(splitOff);
                Check("the patch picked is the one under the mouse, up to the side they share", switchAt > 0 && picked.Take(switchAt).All(e => e == Element<TerrainPatch>(source))
                    && picked.Skip(switchAt).All(e => e == splitOff));
            }
            var showOutline = builder.elementPicker.GetType().GetMethod("ShowOutline", flags);
            bool Outlined(Node3D node) => RuntimeGizmos.SelectionOutline.GetRenderers(node).Any(r => (r.Layers & ListHighlight.Layer) != 0);
            showOutline.Invoke(builder.elementPicker, new object[] { splitOff, true });
            Check("the element under the mouse is outlined", Outlined(splitOff));
            Check("a patch without a shared side is not accepted", !builder.elementPicker.Pick(Element<TerrainPatch>(far)) && builder.elementPicker.IsActive());
            Check("the patch sharing a side is", builder.elementPicker.Pick(splitOff) && !builder.elementPicker.IsActive() && !ListHighlight.suspended);
            M.ProcessUpdate(); await Frames(2);
            Check("the picked patch is merged into the edited one", M.patches.Count == patchCount && Element<TerrainPatch>(source).GetPerimeterPointCount() == 5 && Shown() == patchPanel);
            await Call("history.undo"); await Call("history.undo");
            Check("merge and split are one undo step each", M.patches.Count == patchCount && Element<TerrainPatch>(source).GetPerimeterPointCount() == 4);

            //the eyedropper: the element of the open editor gets the properties of the element clicked
            await Call("state.setBuiltin", new { @ref = far, name = "smooth", value = 5 });
            await Edit(Element<TerrainPatch>(source));
            CallBuilder<object>("StartPropertyCopy");
            Check("the eyedropper starts over the open editor", builder.elementPicker.IsActive() && Shown() == patchPanel);
            Check("an element of another kind is not accepted", !builder.elementPicker.Pick(Element<Road>(road)));
            Check("an element of the same kind is", builder.elementPicker.Pick(Element<TerrainPatch>(far)));
            await Frames(2);
            Check("the edited element gets its properties", Element<TerrainPatch>(source).state.Int("smooth") == 5);
            await Call("history.undo");
            Check("the copy is an undo step", Element<TerrainPatch>(source).state.Int("smooth") == 3);
            if (builder.elementPicker.IsActive()) builder.elementPicker.Stop();
            await Close();
            CallBuilder<object>("StartPropertyCopy");
            Check("without an open editor the eyedropper explains itself", builder.AlertActive() && !builder.elementPicker.IsActive());
            CloseAlert(); await Frames(2);

            //the building line editor: split at the selected point, join with the line clicked
            var linePanel = PanelOf<EditorPanels.Buildings.LineEditorPanel>("buildingLineEditorPanel");
            var edited = Element<BuildingLine>(line);
            History.UndoManager.Record("edit", () => builder.SelectObject(edited, true, null));
            await Frames(2);
            Check("the line editor has the split and join buttons", Shown() == linePanel && ButtonOf(linePanel, "BL_SPLIT") != null && ButtonOf(linePanel, "BL_MERGE") != null);
            var lineCount = M.buildings.Count;
            var linePointCount = edited.GetPointCount();
            var lineBuildingCount = edited.buildings.Count;
            var linePoints = edited.GetPointsComponents();
            var middle = (linePoints[2].GetPoint() + linePoints[3].GetPoint()) * 0.5f;
            await Press(linePanel, "BL_SPLIT");
            Check("the split button starts a pick of a place of the line", outlinePicker.IsActive() && Shown() == linePanel);
            Check("an end of the line is not accepted", !outlinePicker.Pick(outlinePicker.PlaceNear(linePoints[0].GetPoint())));
            Check("a position on a segment is", outlinePicker.Pick(outlinePicker.PlaceNear(middle)) && !outlinePicker.IsActive());
            M.ProcessUpdate();
            Check("the edited line is split there, at a point inserted on the segment", M.buildings.Count == lineCount + 1 && edited.GetPointCount() == 4 && Shown() == linePanel
                && edited.GetPointsComponents()[2] == linePoints[2] && Near(edited.GetPointsComponents()[3].GetPoint(), middle.X, middle.Z));
            var lineRest = M.buildings[M.buildings.Count - 1];
            await Press(linePanel, "BL_MERGE");
            Check("the join button picks the other line", builder.elementPicker.IsActive() && builder.elementPicker.Pick(lineRest));
            M.ProcessUpdate(); await Frames(2);
            Check("the picked line is joined to the edited one", M.buildings.Count == lineCount && edited.GetPointCount() == linePointCount + 1 && edited.buildings.Count == lineBuildingCount + 1);

            //the size handles of the building being edited
            History.UndoManager.Record("edit building", () => linePanel.EditBuilding(edited.buildings[0]));
            await Frames(3);
            StaticBody3D SizeHandle(string name) => M.GetChildren().OfType<StaticBody3D>().FirstOrDefault(h => h.Name == name && h.ProcessMode != Node.ProcessModeEnum.Disabled);
            var heightHandle = SizeHandle("BuildingHeightHandle");
            var depthHandle = SizeHandle("BuildingDepthHandle");
            var building = edited.buildings[0];
            var height = building.state.Float("height");
            var depth = building.state.Float("depth");
            Check("the edited building has its size sides, its top and its back, with the gizmo targets at their middles", heightHandle != null && depthHandle != null
                && Mathf.Abs(GO.GetPosition(heightHandle).Y - building.height) < 0.01f
                && Mathf.Abs(new Vector2(GO.GetPosition(depthHandle).X - GO.GetPosition(heightHandle).X, GO.GetPosition(depthHandle).Z - GO.GetPosition(heightHandle).Z).Length() - depth * 0.5f) < 0.01f);
            if (heightHandle != null && depthHandle != null) {
                bool Drawn(StaticBody3D side) => side.GetChildren().OfType<MeshInstance3D>().Any(m => m.Visible && m.Mesh is ImmediateMesh mesh && mesh.GetSurfaceCount() > 0);
                Check("their contours are drawn", Drawn(heightHandle) && Drawn(depthHandle));
                //a face without width (two points of the front at the same position) has no collider, which couldn't be built
                List<CollisionShape3D> FaceShapes() => heightHandle.GetChildren().OfType<CollisionShape3D>().Where(c => !(c.Shape is CapsuleShape3D)).ToList();
                building.spline.Insert(1, building.spline[0]);
                linePanel.buildingEditor.Update();
                var faces = FaceShapes();
                Check("a face without width has no collider", faces.Count >= 2 && faces[0].Disabled && !faces[1].Disabled);
                building.spline.RemoveAt(1);
                linePanel.buildingEditor.Update();
                await Frames(3); //the colliders enter the physics space
                var roof = GameEngine.Vector3.DecodePosition(GO.GetPosition(heightHandle));
                var query = PhysicsRayQueryParameters3D.Create(roof + Vector3.Up * 50, roof - Vector3.Up * 0.5f, gizmo.selectionMask);
                var hit = gizmo.GetWorld3D().DirectSpaceState.IntersectRay(query);
                Check("a click on the top of the building selects its top", hit.Count > 0 && hit["collider"].As<Node3D>() == heightHandle);
                var seen = GO.GetPosition(heightHandle);
                await Call("view.camera.set", new { position = new[] { seen.X - 40, seen.Y + 30, seen.Z - 60 }, target = new[] { seen.X, seen.Y - 5, seen.Z } });
                gizmo.ClearTargets();
                gizmo.AddTarget(heightHandle);
                await Frames(3); Screenshot("building_size_sides.png");
                await Drag(heightHandle, () => GO.SetPosition(heightHandle, GO.GetPosition(heightHandle) + new Vector3(3, 7, 0)));
                Check("moving the top handle sets the height, and only that", Mathf.Abs(building.state.Float("height") - (height + 7)) < 0.01f
                    && Mathf.Abs(building.state.Float("depth") - depth) < 0.01f && Mathf.Abs(GO.GetPosition(heightHandle).Y - building.height) < 0.01f);
                var back = (GO.GetPosition(depthHandle) - new Vector3(GO.GetPosition(heightHandle).X, GO.GetPosition(depthHandle).Y, GO.GetPosition(heightHandle).Z)).Normalized();
                await Drag(depthHandle, () => GO.SetPosition(depthHandle, GO.GetPosition(depthHandle) + back * 4));
                Check("moving the back handle sets the depth", Mathf.Abs(building.state.Float("depth") - (depth + 4)) < 0.01f);
                await Call("history.undo");
                edited = Element<BuildingLine>(line);
                Check("each drag of a handle is an undo step", Mathf.Abs(edited.buildings[0].state.Float("depth") - depth) < 0.01f
                    && Mathf.Abs(edited.buildings[0].state.Float("height") - (height + 7)) < 0.01f);
            }
            await Close();
            Check("the handles are hidden with the editor", SizeHandle("BuildingHeightHandle") == null && SizeHandle("BuildingDepthHandle") == null);

            //the multiple selection
            var selectionPanel = PanelOf<EditorPanels.MultiSelectionEditorPanel>("multiSelectionEditorPanel");
            History.UndoManager.Record("select multiple", () => CallBuilder<object>("OpenMultiSelection"));
            await Frames(2);
            var selector = builder.multiSelector;
            Check("the multiple selection opens with its click mode", Shown() == selectionPanel && selector.IsActive() && selector.Selection.Count == 0 && !gizmo.allowDeselect);
            var toggle = selector.GetType().GetMethod("Toggle", flags);
            foreach (var element in new object[] { Element<TerrainPatch>(cornerPatch), Element<Road>(road), Element<TerrainPatch>(target) }) toggle.Invoke(selector, new[] { element });
            await Frames(2);
            var pivot = gizmo.mainTargetRoot;
            Check("the selection has a handle at its center, which the gizmo is on", selector.Selection.Count == 3 && pivot != null && pivot.Name == "MultiSelectionPivot");
            await Call("view.camera.set", new { position = V(60, 220, -420), target = V(60, 0, -250) });
            await Frames(3); Screenshot("multi_selection.png");
            var before = PointOf(cp[0]).GetPoint();
            var roadStart = GO.GetPosition(Element<Road>(road).points[0]);
            if (pivot != null) {
                await Drag(pivot, () => GO.SetPosition(pivot, GO.GetPosition(pivot) + new Vector3(12, 0, -8)));
                Check("moving the handle moves the selected elements", Near(PointOf(cp[0]).GetPoint(), before.X + 12, before.Z - 8)
                    && Near(GO.GetPosition(Element<Road>(road).points[0]), roadStart.X + 12, roadStart.Z - 8));
                Check("the handle is the gizmo target again, without rotation or scale", gizmo.mainTargetRoot == pivot && GO.GetLocalScale(pivot).IsEqualApprox(Vector3.One));
                await Call("history.undo");
                Check("the move of the selection is one undo step", Near(PointOf(cp[0]).GetPoint(), before.X, before.Z)
                    && Near(GO.GetPosition(Element<Road>(road).points[0]), roadStart.X, roadStart.Z));
            }
            //the undo closed the panel (as every change from outside)
            History.UndoManager.Record("select multiple", () => CallBuilder<object>("OpenMultiSelection"));
            await Frames(2);
            foreach (var element in new object[] { Element<TerrainPatch>(cornerPatch), Element<TerrainPatch>(target), Element<Road>(road) }) toggle.Invoke(selector, new[] { element });
            await Press(selectionPanel, "COPY_PROPERTIES_FROM");
            Check("the selection copies properties to its elements of the kind clicked", builder.elementPicker.IsActive() && builder.elementPicker.Pick(Element<TerrainPatch>(far)));
            await Frames(2);
            Check("the patches of the selection got them, the road is as it was", Element<TerrainPatch>(cornerPatch).state.Int("smooth") == 5 && Element<TerrainPatch>(target).state.Int("smooth") == 5);
            selector.SelectAll();
            Check("select all selects every element", selector.Selection.Count == M.roads.Count + M.intersections.Count + M.patches.Count + M.buildings.Count + M.meshes.Count + M.customElements.Count);
            selector.Clear();
            Check("clearing the selection removes the handle from the gizmo", selector.Selection.Count == 0 && gizmo.mainTargetRoot == null);
            toggle.Invoke(selector, new object[] { Element<TerrainPatch>(far) });
            await Press(selectionPanel, "MS_DELETE");
            Check("deleting the selection asks first", builder.AlertActive() && Element<TerrainPatch>(far) != null);
            CloseAlert(); await Frames(2);
            await Close();
            Check("closing the panel ends the selection", !selector.IsActive() && selector.Selection.Count == 0 && gizmo.allowDeselect && gizmo.mainTargetRoot == null);
        }
    }
}
