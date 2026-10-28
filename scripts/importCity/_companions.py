"""Loose companion discovery, prop definitions, race data and object transforms."""
import csv
from functools import lru_cache
import math
import re
from pathlib import Path
import numpy as np
from _formats import FormatError
from _mapping import position


@lru_cache(maxsize=512)
def directory_entries(path):
    return {p.name.lower():p for p in Path(path).iterdir()}


def find(root, relative):
    result=Path(root)
    for part in Path(relative).parts:
        if part in ('..','.') or ':' in part: raise FormatError('companion path must stay inside the source root')
        if not result.is_dir(): return None
        result=directory_entries(str(result)).get(part.lower())
        if result is None:return None
    return result if result.is_file() else None


def rows(path):
    if path is None:return []
    with Path(path).open(encoding='cp1252',newline='') as stream:
        return [[s.strip() for s in row] for row in list(csv.reader(stream))[1:] if row and any(s.strip() for s in row)]


def sections(path):
    result={};current=None
    if path is None:return result
    for raw in Path(path).read_text(encoding='cp1252').splitlines():
        line=raw.split('#',1)[0].strip()
        if not line:continue
        if line.startswith('[') and line.endswith(']'):current=line[1:-1].lower();result[current]=[]
        elif current is not None:result[current].append(line)
    return result


def properties(path):
    result={}
    if path:
        for line in Path(path).read_text(encoding='cp1252').splitlines():
            if '=' in line:
                key,value=line.split('=',1);result[key.strip().lower()]=value.strip()
    return result


def import_rules(city, defs_path, rules_path):
    defs={}
    for cells in rows(defs_path):
        if len(cells)<7:raise FormatError(f'{defs_path}: incomplete prop definition')
        defs[cells[0].lower()]=dict(type='psdl',start=float(cells[1]),elemDistance=float(cells[2]),maxNumber=int(float(cells[3])),
                                  minHorizPos=float(cells[4]),maxHorizPos=float(cells[5]),
                                  meshes=['geometry/'+m+'.pkg' for m in cells[6:] if m])
    rules=[]
    for cells in rows(rules_path):
        entries=[]
        for name in cells[1:]:
            if not name:continue
            if name.lower() not in defs:raise FormatError(f'{rules_path}: missing prop definition {name}')
            entries.append(defs[name.lower()])
        rules.append(dict(type='psdl',elements=entries))
    for pi,path in enumerate(city.psdl['paths']):
        if not path['rooms']:continue
        if path.get('negativeRooms'):city.warn(f'prop path {pi}','negative room-number encoding has unknown semantics and is normalized')
        ri=city.psdl['rooms'][path['rooms'][0]-1]['propRule']
        if ri==0:continue
        if 2*ri>len(rules):city.warn(f'prop path {pi}','prop rule CSV entries are missing');continue
        rule=dict(left=rules[2*(ri-1)],right=rules[2*(ri-1)+1])
        roads=[e for (room,ai),e in city.roads.items() if room in path['rooms'] and e['type'] in ('roadWithSidewalks','dividedRoad')]
        if len(path['rooms'])==1 and len(roads)==1 and 'propRule' not in roads[0]['state']:
            roads[0]['state']['propRule']=rule
            continue
        ribbons=[]
        for side in ('left','right'):
            segments=[]
            for room in path['rooms']:
                for (rid,ai),road in city.roads.items():
                    if rid!=room or road['type'] not in ('roadWithSidewalks','dividedRoad'):continue
                    sections0=[]
                    for j,s in enumerate(road['points']['sections']):
                        inner=s[side+'Road'];outer=s[side+'Sidewalk']
                        ip=city.points[int(inner[1:])]['position']
                        raised=city.point(('curb',inner),[ip[0],ip[1]+0.15,ip[2]],dict(column=inner))
                        left=city.points[int(s['leftRoad'][1:])]['position'];right=city.points[int(s['rightRoad'][1:])]['position']
                        ref=city.point(('propReference',pi,rid,ai,j),[(a+b)/2 for a,b in zip(left,right)],dict(line=[s['leftRoad'],s['rightRoad']]))
                        sections0.append(dict(start=raised,end=outer,reference=ref))
                    segments.append(dict(sections=sections0))
            if segments:ribbons.append(dict(segments=segments))
        if ribbons:
            city.element('__propPath',f'Imported room prop path {pi}',dict(ribbonNames=['left','right'],useDistanceReference=True,propRule=rule),dict(ribbons=ribbons))
            city.warn(f'prop path {pi}','procedural spacing retained; random sequence and native room-path output differ')


def instance_transform(record, warn):
    # Source axes are columns. Reflect both world and model coordinates, matching the native PKG decoder.
    axes=np.array(record['axes'],dtype=float).T
    reflect=np.diag([-1,1,1]);matrix=reflect@axes@reflect
    scale=np.linalg.norm(matrix,axis=0)
    if np.any(scale<1e-8):raise FormatError('INST contains a singular transform')
    rotation=matrix/scale
    if np.linalg.det(rotation)<0:scale[0]*=-1;rotation[:,0]*=-1
    if np.max(np.abs(rotation.T@rotation-np.eye(3)))>1e-4:
        warn('INST '+record['name'],'sheared transform approximated')
        u,s,v=np.linalg.svd(rotation);rotation=u@v
    # Godot uses YXZ Euler order; GameEngine mirrors Z on entry/exit.
    # Program-space quaternion/Euler is obtained by reflecting the rotation in Z first.
    z=np.diag([1,1,-1]);godot=z@rotation@z
    x=math.asin(max(-1,min(1,-godot[1,2])))
    if abs(math.cos(x))>1e-6:y=math.atan2(godot[0,2],godot[2,2]);roll=math.atan2(godot[1,0],godot[1,1])
    else:y=math.atan2(-godot[2,0],godot[0,0]);roll=0
    # GameEngine.SetRotation negates X and Y when converting to Godot.
    return dict(mesh='geometry/'+record['name']+'.pkg',position=position(record['position']),
                rotation=[-math.degrees(x),-math.degrees(y),math.degrees(roll)],scale=scale.tolist(),
                settings=dict(prop=False,instModifiers=record['modifiers']))


def obj(pos, yaw=0, model=None, scale=None):
    result=dict(localPosition=dict(zip('xyz',position(pos))),localRotation=dict(x=0,y=yaw,z=0))
    if model:result['meshPath']='geometry/'+model+'.pkg'
    if scale:result['localScale']=dict(zip('xyz',scale))
    return result


def import_settings(city, root, name):
    cinfo_path=find(root,'tune/'+name+'.cinfo')
    ai_path=find(root,'city/'+name+'.aimap')
    if not cinfo_path:city.warn('tune/'+name+'.cinfo','optional companion is missing')
    if not ai_path:city.warn('city/'+name+'.aimap','optional companion is missing')
    cinfo=properties(cinfo_path)
    if 'localizedname' in cinfo:city.properties['cityName']=cinfo['localizedname']
    city.properties['cityFileName']=name
    ai=sections(ai_path)
    if ai.get('speed limit'):city.properties['speedLimit']=float(ai['speed limit'][0])
    if ai.get('ambients drive on the left'):city.properties['driveOnLeft']=bool(int(ai['ambients drive on the left'][0]))
    if ai.get('traffic lights'):
        models=ai['traffic lights'][0].split()
        for i in range(2):city.properties['trafficLight'+str(i+1)]='geometry/'+models[min(i,len(models)-1)]+'.pkg'
    if ai.get('ambient types/density'):
        models=[];last=0
        for line in ai['ambient types/density'][1:]:
            cells=line.split();threshold=float(cells[1]);models.append(dict(carModel='geometry/'+cells[0]+'.pkg',frequency=(threshold-last)*10000));last=threshold
        city.properties['trafficCars']=models
    if ai.get('goodweatherpedname / badweatherpedname'):
        city.properties['pedModels']=[dict(zip(('goodWeatherPedName','badWeatherPedName'),line.split()[:2])) for line in ai['goodweatherpedname / badweatherpedname'][1:]]
    race_dir=cinfo.get('racedir',name)
    if '/' in race_dir or '\\' in race_dir or race_dir in ('.','..'):raise FormatError('invalid CINFO RaceDir')
    def aimap(path):
        data=sections(path);result={}
        for source,target in (('density','trafficDensity'),('speed limit','speedLimit')):
            if data.get(source):result[target]=float(data[source][0])
        police=[]
        for line in data.get('police',[])[1:]:
            c=line.split()
            if len(c)<5:continue
            # The builder exports full transforms; stock link-based police entries have no transform.
            if len(c)>=9:police.append(dict(carModel=obj(list(map(float,c[1:4])),float(c[4]),c[0])))
            else:city.warn(str(path),'link-based police placement omitted')
        result['policeCars']=dict(policeCars=police)
        opponents=[]
        for line in data.get('opponent',[])[1:]:
            c=line.split()
            if len(c)<2:continue
            op=find(root,'race/'+race_dir+'/'+c[1]);waypoints=rows(op)
            if not waypoints:continue
            first=list(map(float,waypoints[0][:4]))
            item=dict(carModel=obj(first[:3],first[3],c[0]),waypoints=[dict(waypoint=obj(list(map(float,row[:3])))) for row in waypoints[1:]])
            for index,key in ((2,'speedMultiplier'),(4,'cautionInCorners'),(5,'cautionInCornersThreshold'),(11,'brakingBias')):
                if len(c)>index:item[key]=float(c[index])
            for index,key in ((6,'avoidTraffic'),(7,'avoidProps'),(8,'avoidPlayers'),(9,'avoidOpponents'),(10,'badPathfinding')):
                if len(c)>index:item[key]=bool(int(c[index]))
            opponents.append(item)
        result['opponents']=dict(opponents=opponents)
        for key in ('exceptions','hookmen'):
            if data.get(key) and data[key][0]!='0':city.warn(str(path),key+' entries are not represented')
        return result
    roam_path=find(root,'race/'+race_dir+'/roam.aimap')
    if roam_path:
        roam=aimap(roam_path)
        if roam.get('policeCars'):city.properties['roamPoliceCars']=roam['policeCars']
    for prefix,key,ckey in (('blitz','blitzRaces','blitznames'),('circuit','circuitRaces','circuitnames'),('race','checkpointRaces','checkpointnames')):
        names=cinfo.get(ckey,'').split('|');races=[]
        for i,row in enumerate(rows(find(root,'race/'+race_dir+'/mm'+prefix+'data.csv'))):
            values=[float(c or 0) if j else c for j,c in enumerate(row)]
            race=dict(name=names[i] if i<len(names) else prefix+str(i))
            for index,param in ((2,'timeOfDay'),(3,'weather'),(6,'trafficDensity'),(7,'pedestriansDensity'),(8,'laps'),(9,'timeLimit'),(12,'timeOfDay_professional'),(13,'weather_professional'),(17,'pedestriansDensity_professional'),(18,'laps_professional'),(19,'timeLimit_professional')):
                if len(values)>index:race[param]=values[index]
            race_id=prefix+str(i)
            a=aimap(find(root,'race/'+race_dir+'/'+race_id+'.aimap'));race.update(a)
            professional=aimap(find(root,'race/'+race_dir+'/'+race_id+'.aimap_p'))
            for k,v in professional.items():race[k+'_professional']=v
            race['checkpoints']=[dict(checkpoint=obj(list(map(float,c[:3])),float(c[3]),scale=[float(c[4]),1,1])) for c in rows(find(root,'race/'+race_dir+'/'+race_id+'waypoints.csv')) if len(c)>=5]
            races.append(race)
        if races:city.properties[key]=races
    hud=find(root,'tune/'+name+'.mmHudMap')
    if hud:
        match=re.search(r'Ocean\s+Color\s*[=:]?\s*([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)',hud.read_text(encoding='cp1252'))
        if match:city.properties['hudmapColorWater']='#'+''.join(f'{round(max(0,min(1,float(v)))*255):02X}' for v in match.groups())
        city.warn(str(hud),'ocean color imported; map placement/zoom and images are regenerated')
    return race_dir
