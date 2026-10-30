"""Scripts-menu adapter. All selected sources are parsed before the first city mutation."""
import json
import math
from pathlib import Path
from _formats import read_psdl, read_bai, read_inst, read_pathset, FormatError
from _mapping import ImportCity, position
from _companions import find, import_rules, import_settings, instance_transform, obj, properties, directory_entries

SCRIPT=Path(__file__).resolve().parent
APPEND=('blitzRaces','circuitRaces','checkpointRaces')


def strings():
    result=json.loads((SCRIPT/'strings/en-US.json').read_text(encoding='utf-8'))
    settings=SCRIPT.parents[4]/'settings.json'
    try:
        language=json.loads(settings.read_text(encoding='utf-8-sig')).get('Language','en-US')
        if Path(language).name==language and (SCRIPT/'strings'/f'{language}.json').exists():
            result.update(json.loads((SCRIPT/'strings'/f'{language}.json').read_text(encoding='utf-8')))
    except (OSError,ValueError):pass
    return result


def prepare(values):
    directory_entries.cache_clear()
    source=Path(values.get('psdlFile','')).resolve()
    if not source.is_file():raise FormatError('select an existing PSDL file')
    root=Path(values['sourceRoot']).resolve() if values.get('sourceRoot') else source.parent.parent if source.parent.name.lower()=='city' else source.parent
    if not root.is_dir():raise FormatError('source root is not a directory')
    city=ImportCity(read_psdl(source)).geometry()
    name=source.stem
    def companion(relative,enabled=True,parser=None):
        if not enabled:return None
        path=find(root,relative)
        if path is None and relative.startswith('city/'+name):
            path=find(source.parent,relative[len('city/'):])
        if path is None:city.warn(relative,'optional companion is missing');return None
        return parser(path) if parser else path
    bai=companion('city/'+name+'.bai',values.get('importBai',True),read_bai)
    if bai:city.bai(bai)
    if values.get('importInst',True):
        inst=companion('city/'+name+'.inst',True,read_inst)
        if inst:
            for record in inst:city.meshes.append(instance_transform(record,city.warn))
            city.warn('INST','room assignments are recalculated from imported geometry')
    if values.get('importProps',True):
        paths=companion('city/'+name+'/props.pathset',True,read_pathset)
        if paths:city.pathset(paths)
        defs=companion('city/'+name+'/propdefs.csv')
        rules=companion('city/'+name+'/proprules.csv')
        import_rules(city,defs,rules)
    race_dir=properties(find(root,'tune/'+name+'.cinfo')).get('racedir',name)
    if '/' in race_dir or '\\' in race_dir or race_dir in ('.','..'):raise FormatError('invalid CINFO RaceDir')
    if values.get('importSettings',True):race_dir=import_settings(city,root,name)
    if values.get('importPaths',True):
        decals=companion('city/'+name+'/decals.pathset',True,read_pathset)
        for i,path in enumerate(decals or []):
            if path['type'] not in (0,1,2):city.warn(f'decal {i}','unsupported bounded path type omitted');continue
            points=path['points']
            if len(points)<4 or len(points)%2:city.warn(f'decal {i}','invalid strip omitted');continue
            import numpy as np
            pairs=list(zip(points[::2],points[1::2]));widths=[float(np.linalg.norm(np.subtract(a,b))) for a,b in pairs]
            width=sum(widths)/len(widths)
            if max(widths)-min(widths)>0.01:city.warn(f'decal {i}','variable width approximated by average')
            ids=[city.point(('decal',i,k),position([(a[j]+b[j])/2 for j in range(3)])) for k,(a,b) in enumerate(pairs)]
            city.element('decal',f'Imported decal {i}',dict(texture='texture/'+path['name']+'.tex',width=width,curveType=2),dict(spline=ids))
        trains=companion('race/'+race_dir+'/'+name+'_train.pathset',True,read_pathset)
        for i,path in enumerate(trains or []):
            if path['type']!=2:city.warn(f'train path {i}','unsupported train path omitted');continue
            if len(path['points'])<3:city.warn(f'train path {i}','incomplete train path retained for editing; at least three points are needed to export')
            if path['spacing'] not in (0,20):city.warn(f'train path {i}','train spacing is regenerated as 5 m')
            ids=[city.point(('train',i,k),position(p)) for k,p in enumerate(path['points'])]
            city.element('train',path['name'] or f'Imported train {i}',dict(curveType=3),dict(spline=ids))
    def finite(value):
        if isinstance(value,float) and not math.isfinite(value):raise FormatError('non-finite numeric value in companion data')
        if isinstance(value,dict):
            for child in value.values():finite(child)
        elif isinstance(value,list):
            for child in value:finite(child)
    finite(city.payload());finite(city.meshes);finite(city.properties)
    return city,root


def main():
    import citybuilder as cb
    text=strings()
    info=cb.api.city.info()
    if not info.get('loaded') or info.get('core')!='MidtownMadness2':raise SystemExit(text['IMPORT_CITY_WRONG_CORE'])
    values=cb.inputs()
    cb.progress(0,text['IMPORT_CITY_CHECKING'])
    city,root=prepare(values)
    project=cb.api.project.settings.get()
    before=project['extraFolders']
    roots=[root,Path(info['folder']),SCRIPT.parents[3]/'common/MidtownMadness2']+[Path(p) for p in before+project.get('globalExtraFolders',[])]
    assets=set()
    def collect(value):
        if isinstance(value,str) and value.lower().startswith(('geometry/','texture/')):assets.add(value)
        elif isinstance(value,dict):
            for v in value.values():collect(v)
        elif isinstance(value,list):
            for v in value:collect(v)
    collect(city.elements);collect(city.meshes);collect(city.properties)
    for asset in sorted(assets):
        if not any(find(r,asset) for r in roots):city.warn(asset,'asset is missing; editor fallback is used')
    folders=list(before)
    if str(root).lower() not in [p.lower() for p in folders]:folders.append(str(root))
    try:
        cb.api.project.settings.set(extraFolders=folders)
        cb.api.api.configure(autoFlush=False)
        cb.progress(0.2,text['IMPORT_CITY_GEOMETRY'])
        result=cb.call('lowLevel.import',data=city.payload())
        for start in range(0,len(city.meshes),100):
            cb.batch([('meshes.create',m) for m in city.meshes[start:start+100]])
            cb.progress(0.4+0.4*min(start+100,len(city.meshes))/max(len(city.meshes),1),text['IMPORT_CITY_OBJECTS'])
        properties=city.properties if values.get('applySourceSettings',True) else {k:v for k,v in city.properties.items() if k in APPEND}
        schema=cb.api.state.schema(ref=0)
        allowed={p['name'] for p in schema['parameters']}
        for key in list(properties):
            if key not in allowed:city.warn(key,'property is unavailable in this core version');properties.pop(key)
        if properties:cb.call('state.import',ref=0,values=properties,append=list(APPEND))
        cb.api.city.flush()
    except BaseException:
        cb.api.project.settings.set(extraFolders=before)
        raise
    for warning in city.warnings:cb.log(json.dumps(warning,ensure_ascii=False),level='warning')
    cb.progress(1,text['IMPORT_CITY_DONE'])
    cb.alert(text['IMPORT_CITY_SUMMARY'].format(elements=len(city.elements),objects=len(city.meshes),warnings=len(city.warnings)),text['IMPORT_CITY_TITLE'])


if __name__=='__main__':
    try:main()
    except (FormatError,OSError,ValueError,KeyError) as error:raise SystemExit(strings()['IMPORT_CITY_FAILED'].format(detail=error))
