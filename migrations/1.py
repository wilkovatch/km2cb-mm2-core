import sys, MigrationHelper, copy

dividers = {'None': 0, 'Flat': 1, 'Elevated': 2, 'Wedged': 3}
curve_types = {'Bezier': 0, 'Hermite': 1, 'LowPoly': 2}
rail_types = {'None': 0, 'Rail': 1, 'Wall': 2, 'FlatGallery': 3, 'CurvedGallery': 4}
prop_elems = {}
prop_rules = {}
prop_containers = {}
intersection_vertices = {}

def safe_pop(a, k):
    if k in a: a.pop(k)

def process_prop_container(old_container):
    if old_container['name'] in prop_containers:
        return
    new_container = {'name': old_container['name'], 'type': 'psdl', 'elements': []}
    for elem in old_container['elems']:
        new_container['elements'].append(prop_elems[elem])
    prop_containers[new_container['name']] = new_container

def process_props(old_prop_rules, data_out):
    data_out['presets']['propElem'] = []
    data_out['presets']['propContainer'] = []
    data_out['presets']['roadPropRule'] = []
    data_out['presets']['terrainPatchBorderMesh'] = []
    data_out['presets']['buildingBlock'] = []
    for k,v in prop_elems.items():
        data_out['presets']['propElem'].append(v)
    i = 1
    for old_rule in old_prop_rules:
        new_rule = {'name': old_rule['name'], 'type': 'psdl'}
        if 'leftRule' in old_rule:
            process_prop_container(old_rule['leftRule'])
            new_rule['left'] = prop_containers[old_rule['leftRule']['name']]
        if 'rightRule' in old_rule:
            process_prop_container(old_rule['rightRule'])
            new_rule['right'] = prop_containers[old_rule['rightRule']['name']]
        data_out['presets']['roadPropRule'].append(new_rule)
        prop_rules[i] = new_rule
        i += 1
    for k,v in prop_containers.items():
        data_out['presets']['propContainer'].append(v)

def process_state(e, container):
    e2 = {}
    e2 = copy.deepcopy(e)
    safe_pop(e2, 'Name') #duplicate of name (lowercase)
    if container == 'roadPresets':
        for k,v in e.items():
            if k == 'railState':
                for k2, v2 in v.items():
                    e2['rail_' + k2] = v2
        safe_pop(e2, 'railState')
        safe_pop(e2, 'uMult')
        safe_pop(e2, 'vMult')
        if 'propRule' in e2 and e2['propRule'] in prop_rules: e2['propRule'] = prop_rules[e2['propRule']]
        else: safe_pop(e2, 'propRule')
        e2['type'] = 'psdl'
        e2['divider'] = dividers[e2['divider']]
        e2['curveType'] = curve_types[e2['curveType']]
        e2['rail_type'] = rail_types[e2['rail_type']]
        safe_pop(e2, 'rail_Name')
    elif container == 'railPresets':
        e2['type'] = rail_types[e2['type']]
    elif container == 'intersectionPresets':
        e2['type'] = 'psdl'
        safe_pop(e2, 'fixSwVerticalUV')
        safe_pop(e2, 'uMult')
        safe_pop(e2, 'vMult')
        safe_pop(e2, 'uMultSW')
        safe_pop(e2, 'vMultSW')
    elif container == 'buildingSidePresets':
        e2['type'] = 'psdl'
        safe_pop(e2, 'uMult')
        safe_pop(e2, 'vMult')
        safe_pop(e2, 'paramMeshDict')
        tmpDict = []
        for v in e2['blockDict']:
            tmpV = {}
            tmpV['type'] = v['front']['type'].lower()
            tmpV['assetName'] = v['front']['assetName']
            tmpV['name'] = v['name']
            tmpDict.append(tmpV)
        e2['blockDict'] = tmpDict
        safe_pop(e2['groundFloor'], 'slices')
        if 'upperFloors' in e2:
            for i in range(len(e2['upperFloors'])):
                safe_pop(e2['upperFloors'][i], 'slices')
    elif container == 'buildingPresets':
        e2['type'] = 'psdl'
        safe_pop(e2, 'uMult')
        safe_pop(e2, 'vMult')
        for s in ('front', 'left', 'right', 'back'):
            if s + 'State' in e2:
                e2[s + 'State'] = process_state(e2[s + 'State'], 'buildingSidePresets')
    elif container == 'buildingLinePresets':
        e2['type'] = 'psdl'
        safe_pop(e2, 'uMult')
        safe_pop(e2, 'vMult')
    elif container == 'terrainPatchPresets':
        e2['type'] = 'psdl'
        safe_pop(e2, 'uMult')
        safe_pop(e2, 'vMult')
    elif container == 'terrainPatchRail':
        e2 = {}
        for k,v in e.items():
            if k == 'name': e2[k] = v
            elif k == 'type': e2['rail_' + k] = rail_types[e[k]]
            else: e2['rail_' + k] = v
        e2['type'] = 'psdl'
    elif container == 'instance':
        rail_keys = {
            'continueLeftRailOnStartIntersection': 'rail_continueLeftOnStartIntersection',
            'continueRightRailOnStartIntersection': 'rail_continueRightOnStartIntersection',
            'continueLeftRailOnEndIntersection': 'rail_continueLeftOnEndIntersection',
            'continueRightRailOnEndIntersection': 'rail_continueRightOnEndIntersection',
        }
        for k1, k2 in rail_keys.items():
            if k1 in e2:
                e2[k2] = e2[k1]
                e2.pop(k1)
    return e2

def process_instance_state(e, ie):
    ie2 = process_state(ie, 'instance')
    if 'blockNumber' in e:
        ie2['blockNumber'] = e['blockNumber']
        e.pop('blockNumber')
    return ie2
    
def process_preset_list(data, data_out, container):
    new_key = container[:-7]
    data_out['presets'][new_key] = []
    for e in data[container]:
        e2 = process_state(e, container)
        data_out['presets'][new_key].append(e2)

def process_presets(mh):
    city_data = mh.read_local('city.json.gz', True)
    data = mh.read_and_backup('presets.json', False)
    data_out = {}
    data_out['presets'] = {}
    data_out['presets']['rail'] = [{'type': 0, 'name': 'Default'}]
    for elem in city_data['propElems']:
        safe_pop(elem, 'Name')
        elem['type'] = 'psdl'
        elem['elemDistance'] = elem['distance']
        safe_pop(elem, 'distance')
        prop_elems[elem['name']] = elem
    process_props(city_data['propRules'], data_out)
    for k in data.keys():
        process_preset_list(data, data_out, k)
    mh.save(data_out, 'presets.json', False)

def process_city_object(e, container):
    e2 = {}
    e2 = copy.deepcopy(e)
    if 'metadata' in e:
        for k,v in e['metadata'].items():
            e2['state'][k] = v
        safe_pop(e2, 'metadata')
    if container == 'meshes':
        e2['settings'] = {}
        e2['settings']['prop'] = e2['prop']
        safe_pop(e2, 'prop')
    elif container == 'roads':
        e2['state'] = process_state(e2['state'], 'roadPresets')
        if 'instanceState' in e2: e2['instanceState'] = process_instance_state(e2['state'], e2['instanceState'])
    elif container == 'intersections':
        e2['state'] = process_state(e2['state'], 'intersectionPresets')
        if 'instanceState' in e2: e2['instanceState'] = process_state(e2['state'], e2['instanceState'])
        intersection_vertices[e2['id']] = e2['state']['sidewalkSegments'] + 1 # needed to fix anchors below
    elif container == "terrainPatches":
        e2['state'] = process_state(e2['state'], 'terrainPatchPresets')
        e2['borderMeshes'] = []
        for r in e2['rails']:
            r2 = {}
            r2['state'] = process_state(r['state'], 'terrainPatchRail')
            r2['segmentPointsIds'] = r['segmentPointsIds']
            e2['borderMeshes'].append(r2)
        safe_pop(e2, 'rails')
    elif container == "buildingLines":
        e2['state'] = process_state(e2['state'], 'buildingLinePresets')
        newBuildings = []
        for b in e2['buildings']:
            b2 = process_state(b, 'buildingPresets')
            newBuildings.append(b2)
        e2['buildings'] = newBuildings
        newSides = []
        for s in e2['sides']:
            s2 = process_state(s, 'buildingSidePresets')
            newSides.append(s2)
        e2['sides'] = newSides
    elif container == 'terrainPoints':
        if e2['elementType'] == 'Intersection':
            # Anchor system changed a little (a vertex at the start and another one at the end have been added)
            # so the indices need to be corrected
            i0 = e2['anchorIndex']
            v0 = intersection_vertices[e2['elementId']]
            v1 = v0 + 2
            n0 = i0 // v0
            r0 = i0 % v0
            newIndex = 1 + r0 + n0 * v1
            e2['anchorIndex'] = newIndex
    return e2

def process_city(mh):
    data = mh.read_and_backup('city.json.gz', True)
    data_out = {}
    for k in ('heightmapResolution', 'terrainSize', 'heightMap'):
        data_out[k] = data[k]
    for k in ('meshes', 'roads', 'intersections', 'terrainPoints', 'terrainPatches', 'buildingLines', 'genericObjects'):
        data_out[k] = []
    for k in ('meshes', 'roads', 'intersections', 'terrainPoints', 'terrainPatches', 'buildingLines', 'genericObjects'):
        for e in data[k]:
            data_out[k].append(process_city_object(e, k))
    mh.save(data_out, 'city.json.gz', True)

def process_folder(mh):
    data = mh.read_and_backup('preferences.json', False)
    if mh.get_pref('coreVersion', 0) >= 1: return
    data['core'] = 'MidtownMadness2'
    data['coreVersion'] = 1
    data['programVersion'] = 1
    newFolders = []
    for f in data['extraFolders']:
        if f == '.\\MM2\\':
            newFolders.append('.\\MidtownMadness2\\')
        else:
            newFolders.append(f)
    data['extraFolders'] = newFolders
    safe_pop(data, 'curTerrainUMult')
    safe_pop(data, 'curTerrainVMult')
    mh.save(data, 'preferences.json', False)
    process_presets(mh)
    process_city(mh)

mh = MigrationHelper.MigrationHelper(sys.argv[1])
process_folder(mh)
print('done 1')
