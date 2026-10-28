"""Semantic audit of loose MM2 city round trips. Never modifies either city.

python _roundtrip_check.py source/city/a.psdl exported/city/a.psdl --sample 10 --seed 42
The JSON report distinguishes geometry, topology, lane curves, pedestrian curves and placements.
Use --strict to return failure when the compared representations differ.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random
import numpy as np
from _formats import read_psdl, read_bai, read_inst, read_pathset
from _mapping import ImportCity
from _companions import find, properties


def coord(value):return tuple(round(float(c),3) for c in value)


def geometry(source):
    city=ImportCity(source).geometry();points={p['id']:p['position'] for p in city.points};result=Counter()
    def leaves(node):
        if isinstance(node,str):yield points[node]
        elif isinstance(node,dict):
            for v in node.values():yield from leaves(v)
        elif isinstance(node,list):
            for v in node:yield from leaves(v)
    for e in city.elements:
        typ=e['type']
        if typ=='room':continue
        state=e['state']
        mats=tuple(sorted((k,v.lower()) for k,v in state.items() if 'texture' in k.lower() and isinstance(v,str)))
        if 'mesh' in e:
            vs=e['mesh']['vertices'];ts=e['mesh']['triangles']
            for i in range(0,len(ts),3):
                result[('surface',mats,tuple(sorted(coord(points[vs[j]]) for j in ts[i:i+3])))]+=1
        else:
            result[(typ,mats,tuple(sorted(coord(p) for p in leaves(e.get('points',{})))) )]+=1
    return result


def curve_error(a,b):
    if not a or not b:return None if bool(a)!=bool(b) else 0.0
    def directed(points,line):
        if len(line)==1:return max(float(np.linalg.norm(np.subtract(p,line[0]))) for p in points)
        worst=0.0
        for p in points:
            p=np.array(p);best=float('inf')
            for x,y in zip(line,line[1:]):
                x,y=np.array(x),np.array(y);delta=y-x;length=float(np.dot(delta,delta))
                t=max(0,min(1,float(np.dot(p-x,delta))/length)) if length>1e-12 else 0
                best=min(best,float(np.linalg.norm(p-x-t*delta)))
            worst=max(worst,best)
        return worst
    return max(directed(a,b),directed(b,a))


def section_error(source_center,source_curve,target_center,target_curve):
    """Compare section samples at corresponding road positions, rather than only curve shapes."""
    worst=0.0
    for center,value in zip(target_center,target_curve):
        best=float('inf');expected=None
        for i,(a,b) in enumerate(zip(source_center,source_center[1:])):
            a,b,p=np.asarray(a),np.asarray(b),np.asarray(center)
            delta=b-a;length=float(np.dot(delta,delta))
            t=max(0,min(1,float(np.dot(p-a,delta))/length)) if length>1e-12 else 0
            distance=float(np.linalg.norm(p-a-t*delta))
            if distance<best:
                best=distance;expected=(1-t)*np.asarray(source_curve[i])+t*np.asarray(source_curve[i+1])
        if expected is not None:worst=max(worst,float(np.linalg.norm(np.asarray(value)-expected)))
    return worst


def path_placements(paths):
    result=Counter()
    for path in paths:
        pts=path['points'];name=path['name'].lower()
        if path['type']==0:
            for p in pts:result[(name,coord(p),0.0)]+=1
        elif path['type']==1:
            for a,b in zip(pts[::2],pts[1::2]):
                d=np.subtract(b,a);yaw=round(math.degrees(math.atan2(d[2],d[0]))%360,1)
                result[(name,coord(a),yaw)]+=1
        else:
            spacing=path['spacing']/4 if path['spacing'] else 5
            for a,b in zip(pts,pts[1:]):
                d=np.subtract(b,a);length=float(np.linalg.norm(d))
                if length<1e-6:continue
                yaw=round(math.degrees(math.atan2(d[2],d[0]))%360,1)
                for i in range(max(1,int(length/spacing))):result[(name,coord(np.add(a,d*(i*spacing/length))),yaw)]+=1
    return result


def audit(first,second,sample=10,seed=42):
    first,second=Path(first),Path(second)
    a,b=read_psdl(first),read_psdl(second)
    ga,gb=geometry(a),geometry(b)
    report=dict(psdl=dict(sourceRooms=len(a['rooms']),exportedRooms=len(b['rooms']),
                          missingGeometry=sum((ga-gb).values()),extraGeometry=sum((gb-ga).values())))
    def portals(source):
        centers={i+1:coord(np.mean([source['vertices'][v] for v,n in room['perimeter']],axis=0)) for i,room in enumerate(source['rooms']) if room['perimeter']}
        result=Counter()
        for i,room in enumerate(source['rooms'],1):
            per=room['perimeter']
            for j,(v,n) in enumerate(per):
                other=per[(j+1)%len(per)][0]
                if v!=other:result[(coord(source['vertices'][v]),coord(source['vertices'][other]),centers.get(n))]+=1
        return result
    pa,pb=portals(a),portals(b)
    report['psdl'].update(missingPortalEdges=sum((pa-pb).values()),extraPortalEdges=sum((pb-pa).values()))
    root_a=first.parent.parent if first.parent.name.lower()=='city' else first.parent
    root_b=second.parent.parent if second.parent.name.lower()=='city' else second.parent
    bai_a,bai_b=find(root_a,'city/'+first.stem+'.bai'),find(root_b,'city/'+second.stem+'.bai')
    if bai_a or bai_b:
        aa=read_bai(bai_a) if bai_a else dict(roads=[],intersections=[])
        bb=read_bai(bai_b) if bai_b else dict(roads=[],intersections=[])
        routes=[]
        def connections(data,road):
            result=[]
            for end in ('start','end'):
                iid=road[end]['intersection']
                intersection=next((i for i in data['intersections'] if i['id']==iid),None)
                if intersection is None:result.append(None);continue
                neighbors=sorted((coord(r['center'][0]),coord(r['center'][-1])) for r in data['roads']
                                 if r['id']!=road['id'] and any(r[e]['intersection']==iid for e in ('start','end')))
                result.append((coord(intersection['center']),neighbors))
            return result
        for road in random.Random(seed).sample(aa['roads'],min(sample,len(aa['roads']))):
            if not bb['roads']:routes.append(dict(source=road['id'],missing=True));continue
            def cost(r):return np.linalg.norm(np.subtract(road['center'][0],r['center'][0]))+np.linalg.norm(np.subtract(road['center'][-1],r['center'][-1]))
            other=min(bb['roads'],key=cost)
            item=dict(source=road['id'],matched=other['id'],endpointError=float(cost(other)),sourceSections=road['n'],exportedSections=other['n'],
                      sourceRoomCount=len(road['rooms']),exportedRoomCount=len(other['rooms']),
                      centerError=curve_error(road['center'],other['center']),sourceFlags=road['flags'],exportedFlags=other['flags'],
                      sourceConnections=connections(aa,road),exportedConnections=connections(bb,other),
                      sourceEndRules=[road[e]['rule'] for e in ('start','end')],exportedEndRules=[other[e]['rule'] for e in ('start','end')],sides={})
            for side in ('right','left'):
                x,y=road[side],other[side]
                item['sides'][side]=dict(sourceLanes=x['lanes'],exportedLanes=y['lanes'],sourceAmbient=x['ambient'],exportedAmbient=y['ambient'],
                    laneErrors=[curve_error(v,w) for v,w in zip(x['laneVertices'],y['laneVertices'])],
                    sidewalkError=curve_error(x['sidewalkCenter'],y['sidewalkCenter']),
                    sidewalkSectionError=section_error(road['center'],x['sidewalkCenter'],other['center'],y['sidewalkCenter']),
                    tramErrors=[curve_error(v,w) for v,w in zip(x['tramVertices'],y['tramVertices'])],
                    trainErrors=[curve_error(v,w) for v,w in zip(x['trainVertices'],y['trainVertices'])],
                    sourceRails=[x['trams'],x['trains']],exportedRails=[y['trams'],y['trains']])
            routes.append(item)
        report['bai']=dict(sourceRoutes=len(aa['roads']),exportedRoutes=len(bb['roads']),sourceIntersections=len(aa['intersections']),exportedIntersections=len(bb['intersections']),sample=routes)
    for filename in ('props.pathset','decals.pathset'):
        x=find(root_a,'city/'+first.stem+'/'+filename);y=find(root_b,'city/'+second.stem+'/'+filename)
        if not x and not y:continue
        ap,bp=read_pathset(x) if x else [],read_pathset(y) if y else []
        if filename=='props.pathset':
            x,y=path_placements(ap),path_placements(bp)
        else:
            x=Counter((p['name'].lower(),tuple(coord(v) for v in p['points'])) for p in ap)
            y=Counter((p['name'].lower(),tuple(coord(v) for v in p['points'])) for p in bp)
        report[filename]=dict(sourceRecords=len(ap),exportedRecords=len(bp),missing=sum((x-y).values()),extra=sum((y-x).values()))
    def train_signatures(root,stem):
        race_dir=properties(find(root,'tune/'+stem+'.cinfo')).get('racedir',stem)
        path=find(root,'race/'+race_dir+'/'+stem+'_train.pathset')
        return Counter((p['name'].lower(),p['spacing'],tuple(coord(v) for v in p['points'])) for p in read_pathset(path)) if path else Counter()
    ta,tb=train_signatures(root_a,first.stem),train_signatures(root_b,second.stem)
    if ta or tb:report['trains']=dict(missing=sum((ta-tb).values()),extra=sum((tb-ta).values()))
    x=find(root_a,'city/'+first.stem+'.inst');y=find(root_b,'city/'+second.stem+'.inst')
    if x or y:
        def signatures(records):return Counter((r['name'].lower(),coord(r['position']),r['modifiers'],tuple(coord(v) for v in r['axes'])) for r in records)
        aa,bb=signatures(read_inst(x) if x else []),signatures(read_inst(y) if y else [])
        report['inst']=dict(missing=sum((aa-bb).values()),extra=sum((bb-aa).values()))
    report['notes']=['PSDL prop-rule distribution, native rail motion and unsupported race settings require the importer diagnostics and targeted viewer/game checks.',
                     'BAI distances, frames, culling and traffic-light placement are regenerated; similar lane curves do not imply identical pedestrian or traffic behavior.']
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source');parser.add_argument('exported');parser.add_argument('--sample',type=int,default=10);parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--out');parser.add_argument('--strict',action='store_true');args=parser.parse_args()
    result=audit(args.source,args.exported,args.sample,args.seed);text=json.dumps(result,indent=2)
    if args.out:Path(args.out).write_text(text+'\n',encoding='utf-8')
    print(text)
    changed=any(v.get('missing',0) or v.get('extra',0) or v.get('missingGeometry',0) or v.get('extraGeometry',0) or v.get('missingPortalEdges',0) or v.get('extraPortalEdges',0) for v in result.values() if isinstance(v,dict))
    bai=result.get('bai',{})
    changed |= bai.get('sourceRoutes')!=bai.get('exportedRoutes') or bai.get('sourceIntersections')!=bai.get('exportedIntersections')
    for r in bai.get('sample',[]):
        changed |= r.get('missing',False) or r.get('endpointError',0)>0.03 or r.get('centerError',0)>0.03 or r.get('sourceRoomCount')!=r.get('exportedRoomCount') or r.get('sourceEndRules')!=r.get('exportedEndRules') or r.get('sourceConnections')!=r.get('exportedConnections') or r.get('sourceFlags')!=r.get('exportedFlags')
        for side in r.get('sides',{}).values():
            changed |= side['sourceLanes']!=side['exportedLanes'] or side['sourceAmbient']!=side['exportedAmbient'] or side['sourceRails']!=side['exportedRails'] or (side['sidewalkError'] or 0)>0.03 or side['sidewalkSectionError']>0.03 or any((error or 0)>0.03 for error in side['laneErrors']+side['tramErrors']+side['trainErrors'])
    raise SystemExit(1 if args.strict and changed else 0)
