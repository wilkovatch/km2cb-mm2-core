"""Optional bounded stock check: five fixed-seed routes per city, read-only source assets.

Run through the builder's script CLI with KM2_IMPORT_TEST_FOLDER and KM2_MM2_SOURCE_ROOT set.
Only rooms needed by the ten sampled routes and their endpoints are imported/exported.
"""
import json
import os
from pathlib import Path
import random
import numpy as np
import citybuilder as cb
from _formats import read_psdl,read_bai
from _mapping import ImportCity
from _roundtrip_check import geometry,curve_error,section_error

root=Path(os.environ['KM2_MM2_SOURCE_ROOT']);scratch=Path(os.environ['KM2_IMPORT_TEST_FOLDER'])
scratch.mkdir(parents=True,exist_ok=True)
reports=[]
for name in ('sf','london'):
    psdl=read_psdl(root/'city'/f'{name}.psdl');bai=read_bai(root/'city'/f'{name}.bai')
    roads=random.Random(42).sample(bai['roads'],5)
    ids={r[e]['intersection'] for r in roads for e in ('start','end')}
    intersections=[i for i in bai['intersections'] if i['id'] in ids]
    room_ids={room for r in roads for room in r['rooms']}|{i['room'] for i in intersections}
    city=ImportCity(psdl).geometry(room_ids);city.bai(dict(roads=roads,intersections=intersections))
    cb.api.city.new(folder=str(scratch/name),core='MidtownMadness2',template='SF',terrainSize=8192,heightmapResolution=512)
    cb.api.project.settings.set(extraFolders=[str(root)])
    cb.call('lowLevel.import',data=city.payload())
    path=scratch/name/'export'/f'{name}.psdl'
    cb.api.city.exportJson(path=str(scratch/name/'input.json'))
    try:
        cb.api.city.export(path=str(path),exporter='psdl',flags=dict(propRules=False,inst=False,bai=True,pathset=False,cinfo_aimap=False,hudmap=False,pkgs=False))
    except cb.ApiError as error:
        print(json.dumps(error.details,indent=2));raise
    exported=read_psdl(path.parent/'city'/path.name);out=read_bai(path.parent/'city'/f'{name}.bai')
    original=dict(psdl,rooms=[r for i,r in enumerate(psdl['rooms'],1) if i in room_ids])
    a,b=geometry(original),geometry(exported)
    report=dict(city=name,rooms=len(room_ids),elements=len(city.elements),missingGeometry=sum((a-b).values()),extraGeometry=sum((b-a).values()),routes=[])
    assert len(out['roads'])==5,(name,len(out['roads']))
    for route in roads:
        def cost(r):return np.linalg.norm(np.subtract(r['center'][0],route['center'][0]))+np.linalg.norm(np.subtract(r['center'][-1],route['center'][-1]))
        other=min(out['roads'],key=cost)
        item=dict(id=route['id'],centerError=curve_error(route['center'],other['center']),sourceSections=route['n'],exportedSections=other['n'],sourceRooms=len(route['rooms']),exportedRooms=len(other['rooms']))
        for side in ('right','left'):
            x,y=route[side],other[side]
            assert x['lanes']==y['lanes'] and x['ambient']==y['ambient'],(name,route['id'],side)
            item[side+'LaneError']=max((curve_error(v,w) for v,w in zip(x['laneVertices'],y['laneVertices'])),default=0)
            item[side+'SidewalkError']=curve_error(x['sidewalkCenter'],y['sidewalkCenter'])
            item[side+'SidewalkSectionError']=section_error(route['center'],x['sidewalkCenter'],other['center'],y['sidewalkCenter'])
            assert item[side+'LaneError']<0.031,(name,item)
        report['routes'].append(item)
    reports.append(report)
    cb.api.city.close()
(scratch/'stock-report.json').write_text(json.dumps(reports,indent=2))
print(json.dumps(reports))
