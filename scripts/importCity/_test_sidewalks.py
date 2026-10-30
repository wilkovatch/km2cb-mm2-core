"""Builder CLI regression: -- script <this file>, KM2_IMPORT_TEST_FOLDER=<new scratch folder>.

Optionally set KM2_MM2_SOURCE_ROOT to also check ten fixed-seed stock sidewalk attributes.
"""
import copy
import os
from pathlib import Path
import random
import numpy as np
import citybuilder as cb
from DecodeExportedJson import DecodeExportedJson
from _formats import read_psdl
from _mapping import ImportCity, position
from _test_import_city import fixture_psdl


scratch=Path(os.environ['KM2_IMPORT_TEST_FOLDER'])


def check(name, source):
    city=ImportCity(source).geometry()
    expected={e['name']:e for e in city.elements if e['type']!='room'}
    points={p['id']:p['position'] for p in city.points}
    cb.api.city.new(folder=str(scratch/name),core='MidtownMadness2',template='SF',terrainSize=512,heightmapResolution=512)
    cb.call('customElement.import',data=city.payload())
    cb.api.history.undo()
    assert not cb.api.elements.list(kind='customElement')
    cb.api.history.redo()

    def verify():
        elements=cb.api.elements.list(kind='customElement')
        assert len(elements)==len(city.elements)
        for element in elements:
            if element['name'] not in expected:continue
            e=expected[element['name']]
            geometry=DecodeExportedJson().uncompress_dict(cb.api.elements.geometry(ref=element['id']))['element']
            actual=geometry['points']
            vertices=geometry['data']['mesh']['vertices']
            allowed=[]
            if e['type']=='sidewalkCap':
                assert geometry['data']['fields']['state']['which']==e['state']['which']
                for key in ('a','b'):
                    np.testing.assert_allclose(actual[key]['position'],points[e['points'][key]],atol=0.001)
                a,b=(points[e['points'][key]] for key in ('a','b'))
                allowed=[a,b,np.add(a,[0,0.15,0])]
            else:
                for a,b in zip(actual['sections'],e['points']['sections']):
                    for key in ('inner','outer'):
                        np.testing.assert_allclose(a[key]['position'],points[b[key]],atol=0.001)
                    inner,outer=(points[b[key]] for key in ('inner','outer'))
                    allowed.extend([inner,outer,np.add(inner,[0,0.15,0])])
            assert vertices,(name,e['name'],'empty mesh')
            assert all(min(np.linalg.norm(np.subtract(v,p)) for p in allowed)<0.001 for v in vertices),(name,e['name'],'unexpected mesh vertex')

    cb.api.city.flush();verify()
    cb.api.city.save();cb.api.city.reload();verify()
    cb.api.city.export(path=str(scratch/name/'out'/f'{name}.psdl'),exporter='psdl',flags=dict(bai=False,inst=False,pathset=False,propRules=False,cinfo_aimap=False,hudmap=False,pkgs=False))
    exported=read_psdl(scratch/name/'out/city'/f'{name}.psdl')
    attrs=[a for room in exported['rooms'] for a in room['attributes'] if a['type']==1]
    assert len(attrs)==len(expected),(name,len(attrs),len(expected))
    for e in expected.values():
        cap=e['type']=='sidewalkCap'
        wanted=[points[e['points'][key]] for key in ('a','b')] if cap else [points[s[key]] for s in e['points']['sections'] for key in ('inner','outer')]
        matches=[]
        for a in attrs:
            vs=a['vertices']
            is_cap=len(vs)==4 and vs[0]==vs[1] and vs[0] in (0,1)
            if is_cap!=cap or (cap and vs[0]+1!=e['state']['which']):continue
            actual=[position(exported['vertices'][v]) for v in (vs[2:] if cap else vs)]
            if len(actual)==len(wanted):matches.append(max(np.linalg.norm(np.subtract(x,y)) for x,y in zip(actual,wanted)))
        assert matches and min(matches)<0.04,(name,e['name'],matches)
    cb.api.city.close()
    print(f'{name}: {len(expected)} sidewalks, geometry, undo/redo, save/reload and PSDL re-export OK')


source=fixture_psdl()
# Distinctive unused marker vertices expose accidentally resolving 0/1 as geometry.
source['vertices'][:2]=[[0,-0.15,0],[900,900,900]]
source['rooms'][0]['perimeter']=[[2,0],[3,0],[7,0],[6,0]]
source['rooms'][0]['attributes']=[dict(type=10,texture=0),
    dict(type=1,vertices=[0,0,2,3]),dict(type=1,vertices=[1,1,6,7]),
    dict(type=1,vertices=[2,3,6,7])]
check('synthetic',source)

root=os.environ.get('KM2_MM2_SOURCE_ROOT')
if root:
    for name in ('sf','london'):
        source=read_psdl(Path(root)/'city'/f'{name}.psdl')
        caps,strips=[],[]
        for room in source['rooms']:
            texture=-1
            for a in room['attributes']:
                if a['type']==10:texture=a['texture']
                if a['type']!=1:continue
                vs=a['vertices'];cap=len(vs)==4 and vs[0]==vs[1] and vs[0] in (0,1)
                (caps if cap else strips).append((room,texture,a))
        rng=random.Random(42)
        chosen=[rng.choice([c for c in caps if c[2]['vertices'][0]==marker]) for marker in (0,1)]
        chosen+=rng.sample(strips,3)
        sampled=copy.copy(source);sampled['rooms']=[]
        for room,texture,a in chosen:
            room=copy.copy(room)
            room['attributes']=[dict(type=10,texture=texture),a]
            sampled['rooms'].append(room)
        check(name,sampled)
