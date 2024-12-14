import sys, MigrationHelper, copy

def safe_pop(a, k):
    if k in a: a.pop(k)

def process_instance_state(s):
    res = copy.deepcopy(s)
    if 'doNotStopOnStartIntersection' in res:
        dont_stop_start = res['doNotStopOnStartIntersection']
        res['start_rule'] = 3 if dont_stop_start else 0
        safe_pop(res, 'doNotStopOnStartIntersection')
    if 'doNotStopOnEndIntersection' in res:
        dont_stop_end = res['doNotStopOnEndIntersection']
        res['end_rule'] = 3 if dont_stop_end else 0
        safe_pop(res, 'doNotStopOnEndIntersection')
    return res

def process_road(e):
    if 'instanceState' in e:
        e['instanceState'] = process_instance_state(e['instanceState'])
    return e

def process_city(mh):
    data = mh.read_and_backup('city.json.gz', True)
    for i in range(len(data['roads'])):
        e = data['roads'][i]
        data['roads'][i] = process_road(e)
    mh.save(data, 'city.json.gz', True)

def process_folder(mh):
    data = mh.read_and_backup('preferences.json', False)
    if mh.get_pref('coreVersion', 0) >= 2: return
    data['coreVersion'] = 2
    data['coreFeatureVersion'] = 3
    mh.save(data, 'preferences.json', False)
    process_city(mh)

mh = MigrationHelper.MigrationHelper(sys.argv[1])
process_folder(mh)
print('done 2')
