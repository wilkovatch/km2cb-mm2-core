"""Run with the builder CLI: -- script <this file>, KM2_IMPORT_TEST_FOLDER=<new scratch folder>."""
import copy
import math
import json
import os
import struct
import numpy as np
import sys
from pathlib import Path
import citybuilder as cb
from DecodeExportedJson import DecodeExportedJson
from _test_import_city import write_psdl, write_pathset, fixture_psdl
from _formats import read_psdl, read_pathset, read_inst

folder=Path(os.environ['KM2_IMPORT_TEST_FOLDER'])
folder.mkdir(parents=True,exist_ok=True)
source=folder/'source';(source/'city/synthetic').mkdir(parents=True);(source/'geometry').mkdir()
write_psdl(source/'city/synthetic.psdl')
write_pathset(source/'city/synthetic/props.pathset',[
    dict(name='test',type=2,spacing=0,points=[[0,0,1],[0,0,18]]),
    dict(name='test',type=2,spacing=7,points=[[1,0,1],[1,0,18]]),
    dict(name='test',type=2,spacing=0,points=[[2,0,1],[2,0,8],[2,0,8],[3,0.5,10],[5,1,20]])])
angle=0.4
rotation=np.array([[math.cos(angle),0,math.sin(angle)],[math.sin(angle)**2,math.cos(angle),-math.sin(angle)*math.cos(angle)],[-math.cos(angle)*math.sin(angle),math.sin(angle),math.cos(angle)**2]])
axes=(rotation@np.diag([1.25,1.5,0.75])).T.tolist()
(source/'city/synthetic.inst').write_bytes(struct.pack('<HHB',1,513,0x85)+b'test\0'+struct.pack('<5f',0,-1,2,0,4)
    +struct.pack('<HHB',1,257,5)+b'test\0'+struct.pack('<12f',*(v for a in axes for v in a),0,0,10))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'exporters/psdl'))
from common.pkg_writer import PKGWriter,PKGGroup
group=PKGGroup('test','test')
group.mesh=dict(vertices=[[-0.2,-0.2,0],[0.2,-0.2,0],[0,0.2,1]],normals=[[0,0,1]]*3,uvs=[[0,0],[1,0],[0,1]],submeshes=[([0,1,2],'NONE')])
writer=object.__new__(PKGWriter);writer.geometry_path=str(source/'geometry');writer.write_pkg(group)

(source/'tune').mkdir()
(source/'race/synthetic').mkdir(parents=True)
(source/'tune/synthetic.cinfo').write_text('LocalizedName=Synthetic city\nRaceDir=synthetic\nBlitzNames=Test race\n')
(source/'city/synthetic.aimap').write_text('[Speed Limit]\n14\n[Ambients Drive On The Left]\n1\n[Ambient Types/Density]\n1\ntest 1 0\n')
(source/'race/synthetic/mmblitzdata.csv').write_text('Description,CarType,TimeOfDay,Weather,Opponents,Cops,Ambient,Peds,Laps,Time,Difficulty,ProCarType,ProTime,ProWeather,ProOpponents,ProCops,ProAmbient,ProPeds,ProLaps,ProTime,ProDifficulty\nnone,0,3,2,0,1,0.3,0.4,2,99,1,0,1,3,0,1,0.3,0.5,3,88,1\n')
(source/'race/synthetic/blitz0waypoints.csv').write_text('x,y,z,a,width\n2,0,3,25,5\n3,0,10,45,5\n')
(source/'race/synthetic/blitz0.aimap').write_text('[Density]\n0.3\n[Speed Limit]\n12\n[Police]\n0\n[Opponent]\n0\n')

cb.api.city.new(folder=str(folder/'city'),core='MidtownMadness2',template='SF',terrainSize=512,heightmapResolution=512)
from main import main
cb.call('state.import',ref=0,values=dict(roamPoliceCars=dict(policeCars=[dict(carModel=dict(localPosition=dict(x=1,y=0,z=2)))])))
original_inputs=cb.inputs
cb.inputs=lambda:dict(psdlFile=str(source/'city/synthetic.psdl'),importBai=False,importInst=True,importProps=True,importPaths=False,importSettings=True)
with cb.transaction('test city import'):main()
cb.inputs=original_inputs
paths=cb.api.elements.list(kind='propPath')
assert len(paths)==3,paths
assert len(cb.api.elements.list(kind='lowLevel'))==2
settings=cb.api.state.get(ref=0)['state']
assert settings['cityName']=='Synthetic city' and settings['driveOnLeft']
assert settings['roamPoliceCars']['policeCars'][0]['carModel']['localPosition']['x']==1
assert settings['blitzRaces'][-1]['timeOfDay']==3 and settings['blitzRaces'][-1]['checkpoints'][0]['checkpoint']['localScale']==dict(x=5,y=7.5,z=15)
cb.api.history.undo()
assert not cb.api.elements.list(kind='propPath')
assert not cb.api.elements.list(kind='lowLevel')
cb.api.history.redo()
paths=cb.api.elements.list(kind='propPath')
assert len(paths)==3

def geometry(ref):
    cb.api.city.flush()
    return DecodeExportedJson().uncompress_dict(cb.api.elements.geometry(ref=ref))['element']

assert len(geometry(paths[0]['id'])['data']['propLines'][0]['props'])==3
assert len(geometry(paths[1]['id'])['data']['propLines'][0]['props'])==9
assert len(geometry(paths[2]['id'])['data']['propLines'][0]['props'])==4

# Non-MM2 prop definition: spacing continues across disconnected ribbons without placing in the gap.
pt=lambda p:dict(position=p)
ribbon={'main':[[dict(start=pt([0,0,0]),end=pt([2,0,0])),dict(start=pt([0,0,10]),end=pt([2,0,10]))],
                [dict(start=pt([0,0,20]),end=pt([2,0,20])),dict(start=pt([0,0,30]),end=pt([2,0,30]))]]}
rule=dict(main=dict(type='line',elements=[dict(type='line',mesh='geometry/test.pkg',start=2,elemDistance=5,maxNumber=10,xPos=0.5)]))
# line container has a single element slot; use mixed, which accepts a list of all element types.
rule['main']=dict(type='mixed',elements=rule['main']['elements'])
prop=cb.api.propPaths.create(ribbons=ribbon,rule=rule,name='Generic ribbon')
generic_geometry=geometry(prop)
actual=generic_geometry['data']['propLines'][0]['props']
assert len(actual)==4,(len(actual),actual)
assert [round(p['position'][2]) for p in actual]==[2,7,22,27]
cb.api.propPaths.move(element=prop,offset=[1,0,0]);cb.api.history.undo()
assert cb.api.elements.get(ref=prop,derived=True)['derived']['points']['ribbons'][0]['segments'][0]['sections'][0]['start']['position']==[0,0,0]

# Variable width and a separate distance basis: a 20 m reference over 10 m of geometry.
reference={'main':[[dict(start=pt([0,0,0]),end=pt([2,0,0]),reference=pt([0,0,0])),
                    dict(start=pt([0,0,10]),end=pt([4,0,10]),reference=pt([0,0,20]))]]}
cb.api.propPaths.setRibbons(element=prop,ribbons=reference)
actual=geometry(prop)['data']['propLines'][0]['props']
assert np.max(np.abs(np.array([p['position'] for p in actual])-[[1.1,0,1],[1.35,0,3.5],[1.6,0,6],[1.85,0,8.5]]))<0.0001
# The metadata follows edits to segments and ribbons, including undo/redo.
cb.api.propPaths.insert(element=prop,array='ribbons.0.segments',index=0)
assert cb.api.state.get(ref=prop)['state']['referenceSegments']==['0.1']
cb.api.propPaths.remove(element=prop,array='ribbons.0.segments',index=0)
assert cb.api.state.get(ref=prop)['state']['referenceSegments']==['0.0']
cb.api.history.undo();cb.api.history.redo()
assert cb.api.state.get(ref=prop)['state']['referenceSegments']==['0.0']
cb.api.propPaths.setRibbons(element=prop,ribbons={'main':[reference['main'][0],ribbon['main'][0]]})
cb.api.propPaths.remove(element=prop,array='ribbons.0.segments',index=0)
assert not cb.api.state.get(ref=prop)['state']['useDistanceReference']
cb.api.propPaths.setRibbons(element=prop,ribbons=reference)
# Replacing a rule retains existing points and creates geometry for new container names, as presets do.
rule['extra']=copy.deepcopy(rule['main'])
cb.api.propPaths.setRule(element=prop,rule=rule)
cb.api.city.flush()
derived=cb.api.elements.get(ref=prop,derived=True)['derived']['points']['ribbons']
assert len(derived)==2 and derived[0]['segments'][0]['sections'][1]['end']['position']==[4,0,10]
cb.api.propPaths.removeRibbon(element=prop,index=1)
cb.api.propPaths.delete(element=prop)

# Preflight rejection leaves existing city data intact.
before=len(cb.api.elements.list())
bad=dict(points=[dict(id='a',position=[0,0,0],anchor=dict(column='b')),dict(id='b',position=[0,1,0],anchor=dict(column='a'))],elements=[])
try:cb.call('lowLevel.import',data=bad);raise AssertionError('accepted cyclic anchors')
except cb.ApiError:pass
assert len(cb.api.elements.list())==before

cb.api.city.save()
cb.api.city.reload()
assert len(cb.api.elements.list(kind='propPath'))==3
cb.api.city.exportJson(path=str(folder/'export.json'))
exported=json.loads((folder/'export.json').read_text())
assert len(exported['propPaths'])==3 and len(exported['lowLevelElements'])==2
assert cb.api.state.get(ref=0)['state']['blitzRaces'][-1]['timeOfDay']==3
cb.api.city.export(path=str(folder/'export/synthetic.psdl'),exporter='psdl',flags=dict(bai=False,cinfo_aimap=False,hudmap=False,pkgs=False))
strips=read_pathset(folder/'export/city/synthetic/props.pathset')
assert len(strips)==3 and all(s['type']==2 for s in strips),strips
assert sorted(s['spacing'] for s in strips)==[0,0,7]
inst=read_inst(folder/'export/city/synthetic.inst')
assert len(inst)==2 and inst[0]['modifiers']==513 and inst[1]['modifiers']==257,inst
assert max(abs(a-b) for va,vb in zip(inst[0]['axes'],[[0,0,-1],[0,1,0],[1,0,0]]) for a,b in zip(va,vb))<0.0001,inst
assert max(abs(a-b) for va,vb in zip(inst[1]['axes'],axes) for a,b in zip(va,vb))<0.0001,inst
from _roundtrip_check import audit
report=audit(source/'city/synthetic.psdl',folder/'export/city/synthetic.psdl')
assert report['psdl']['missingGeometry']==0 and report['psdl']['extraGeometry']==0,report
assert report['props.pathset']['missing']==0 and report['props.pathset']['extra']==0,report
(folder/'roundtrip.json').write_text(json.dumps(report,indent=2))

# Standalone PSDL rules must export their evaluated placements, with no native-road suppression.
fallback_rule=dict(main=dict(type='psdl',elements=[dict(type='psdl',meshes=['geometry/test.pkg'],start=2,elemDistance=5,maxNumber=2,minHorizPos=0.2,maxHorizPos=0.8)]))
fallback=cb.api.propPaths.create(ribbons=ribbon,rule=fallback_rule,name='Standalone PSDL fallback')
evaluated=geometry(fallback)['data']['propLines'][0]['props']
assert len(evaluated)==2
cb.api.city.export(path=str(folder/'fallback-export/synthetic.psdl'),exporter='psdl',flags=dict(bai=False,cinfo_aimap=False,hudmap=False,pkgs=False))
fallback_paths=read_pathset(folder/'fallback-export/city/synthetic/props.pathset')
assert len([p for p in fallback_paths if p['type']==2])==3
assert sum(len(p['points'])//2 for p in fallback_paths if p['type']==1)==len(evaluated),fallback_paths
cb.api.propPaths.delete(element=fallback)

# Both preflight errors and failures after mutation leave the appended city intact.
count=len(cb.api.elements.list())
(source/'city/synthetic.bai').write_bytes(b'CAI1')
cb.inputs=lambda:dict(psdlFile=str(source/'city/synthetic.psdl'),importBai=True,importInst=False,importProps=False,importPaths=False,importSettings=False)
from _formats import FormatError
try:
    with cb.transaction('malformed import'):main()
    raise AssertionError('accepted malformed BAI')
except FormatError:pass
finally:cb.inputs=original_inputs
(source/'city/synthetic.bai').unlink()
assert len(cb.api.elements.list())==count
try:
    with cb.transaction('failing append'):
        cb.api.propPaths.create(ribbons=ribbon,rule=rule)
        raise ValueError('rollback test')
except ValueError:pass
assert len(cb.api.elements.list())==count

# A null texture must stay a null PSDL reference, not become a literal 'none' material.
cb.api.city.close()
source_data=fixture_psdl();source_data['nullTexture']=True
write_psdl(source/'city/invisible.psdl',source_data)
cb.api.city.new(folder=str(folder/'invisible'),core='MidtownMadness2',template='SF',terrainSize=512,heightmapResolution=512)
cb.inputs=lambda:dict(psdlFile=str(source/'city/invisible.psdl'),importBai=False,importInst=False,importProps=False,importPaths=False,importSettings=False)
with cb.transaction('invisible geometry import'):main()
cb.inputs=original_inputs
cb.api.city.export(path=str(folder/'invisible-export/invisible.psdl'),exporter='psdl',flags=dict(bai=False,inst=False,pathset=False,propRules=False,cinfo_aimap=False,hudmap=False,pkgs=False))
invisible=read_psdl(folder/'invisible-export/city/invisible.psdl')
assert invisible['rooms'] and any(a['type']==10 for r in invisible['rooms'] for a in r['attributes'])
assert all(a['texture']==-1 for room in invisible['rooms'] for a in room['attributes'] if a['type']==10),invisible
print('Standalone rules, generic sampling, import, undo/redo, reload and native strip/INST round trip: OK')
