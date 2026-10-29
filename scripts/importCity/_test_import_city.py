"""Short synthetic tests; creates no stock fixtures and needs no running builder."""
import copy
import io
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from _formats import Reader, FormatError, attributes, read_psdl, read_pathset, read_inst
from _mapping import ImportCity
from _companions import import_rules, instance_transform

EXPORTER=Path(__file__).resolve().parents[2]/'exporters/psdl'
sys.path.insert(0,str(EXPORTER))
from prop_paths import native_strip, strip_placements
from common.pathset_writer import PATHSETWriter


def fixture_psdl():
    vertices=[[-8,0,0],[-5,0,0],[5,0,0],[8,0,0],[-8,0,20],[-5,0,20],[5,0,20],[8,0,20]]
    return dict(vertices=vertices,heights=[5,0,1],textures=['road','sidewalk','lod','wall','roof','extra','unused'],
        rooms=[dict(flags=12,propRule=1,perimeter=[[0,0],[4,0],[7,0],[3,0]],attributes=[dict(type=10,texture=0),dict(type=0,vertices=list(range(8)))])],
        paths=[dict(rooms=[1])])


def write_psdl(path, source=None):
    source=source or fixture_psdl()
    data=bytearray(b'PSD0'+struct.pack('<II',2,len(source['vertices'])))
    for v in source['vertices']:data.extend(struct.pack('<3f',*v))
    data.extend(struct.pack('<I3f',3,5,0,1))
    data.extend(struct.pack('<I',len(source['textures'])+1))
    for name in source['textures']:
        value=name.encode()+b'\0';data.extend(bytes([len(value)])+value)
    data.extend(struct.pack('<II',2,0))
    words=[0x50,0 if source.get('nullTexture') else 1,0x82]+list(range(8))
    data.extend(struct.pack('<II',4,len(words)))
    for pair in source['rooms'][0]['perimeter']:data.extend(struct.pack('<2H',*pair))
    data.extend(struct.pack('<'+'H'*len(words),*words))
    data.extend(bytes([0,12,0,1])+struct.pack('<10fI',*([0]*10),1))
    data.extend(struct.pack('<IBBH8HBh',0,0,0,0,*([0]*8),1,1))
    Path(path).write_bytes(data)


def write_pathset(path, records):
    data=bytearray(b'PTH1'+struct.pack('<II',len(records),0))
    for record in records:
        data.extend(record.get('name','test').encode().ljust(32,b'\0'))
        pts=record['points'];data.extend(struct.pack('<II',len(pts),0))
        for v in pts:data.extend(struct.pack('<I3f',0,*v))
        data.extend(struct.pack('<BBH',record['type'],record.get('spacing',0),0))
    Path(path).write_bytes(data)


def export_element(points, raw=0):
    expected=strip_placements(points,raw)
    state=dict(ribbonNames=['main'],propRule=dict(main=dict(type='pathsetStrip',elements=[dict(type='pathsetStrip',mesh='geometry/test.pkg',rawSpacing=raw)])))
    e=dict(data=dict(fields=dict(state=state)),points=dict(ribbons=[dict(segments=[dict(sections=[dict(start=dict(position=p),end=dict(position=p)) for p in points])])]))
    placements=[dict(meshId=0,position=p,rotation=[0,math.sin(y/2),0,math.cos(y/2)],scale=[1,1,1]) for p,y in expected]
    return e,placements


class Readers(unittest.TestCase):
    def test_psdl_and_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.psdl';write_psdl(p);source=read_psdl(p)
            city=ImportCity(source).geometry()
            self.assertEqual([e['type'] for e in city.elements],['room','roadWithSidewalks'])
            self.assertEqual(city.elements[1]['points']['sections'][0]['leftSidewalk'],city.elements[0]['points']['perimeter'][0])
            self.assertEqual(city.points[0]['position'],[8,0,0])
            p.write_bytes(p.read_bytes()[:-1])
            with self.assertRaises(FormatError):read_psdl(p)

    def test_all_attribute_lengths(self):
        records=[[0x02]+[0]*8,[0x0a]+[0]*4,[0x12]+[0]*4,[0x1c]+[0]*4,[0x24]+[0]*4,
                 [0x29]+[0]*3,[0x31]+[0]*3,[0x3c]+[0]*4,[0x42,0,256]+[0]*12,
                 [0x48,10]+[0]*10,[0x4a]+[0]*2,[0x50,1],[0x5e]+[0]*6,[0x62,0]+[0]*3]
        for record in records:
            with self.subTest(word=record[0]):self.assertEqual(len(attributes(struct.pack('<'+'H'*len(record),*record),'synthetic')),1)
        with self.assertRaises(FormatError):attributes(struct.pack('<H',0x78),'synthetic')

    def test_bounded_nonfinite(self):
        with self.assertRaises(FormatError):Reader(b'').u32()
        with self.assertRaises(FormatError):Reader(struct.pack('<f',math.inf)).f32()

    def test_null_texture_and_repeated_fan(self):
        source=fixture_psdl();source['rooms'][0]['attributes']=[dict(type=6,vertices=[0,4,7,7,3])]
        city=ImportCity(source).geometry();fan=city.elements[1]
        self.assertTrue(fan['state']['invisible'])
        self.assertEqual(len(fan['mesh']['triangles']),6)
        self.assertEqual(len(fan['mesh']['vertices']),4)

    def test_strip_import_stays_procedural(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'props.pathset';write_pathset(p,[dict(type=2,points=[[0,0,0],[10,0,0]],spacing=7)])
            city=ImportCity(fixture_psdl()).geometry();city.pathset(read_pathset(p))
            self.assertEqual(city.elements[-1]['type'],'__propPath')
            self.assertEqual(city.elements[-1]['state']['propRule']['main']['elements'][0]['rawSpacing'],7)
            self.assertFalse(city.meshes)

    def test_sidewalk_vertex_order(self):
        source=fixture_psdl()
        source['rooms'][0]['attributes']=[dict(type=10,texture=0),dict(type=1,vertices=[2,3,6,7])]
        city=ImportCity(source).geometry();strip=city.elements[1]
        self.assertEqual(strip['type'],'sidewalkStrip')
        self.assertEqual(strip['state']['texture'],'texture/sidewalk.tex')
        for section,inner,outer in zip(strip['points']['sections'],(2,6),(3,7)):
            self.assertEqual(section,dict(inner=city.point_ids[('v',inner,None)],outer=city.point_ids[('v',outer,None)]))

    def test_sidewalk_cap_markers(self):
        for marker in (0,1):
            for texture in (-1,0):
                with self.subTest(marker=marker,texture=texture):
                    source=fixture_psdl()
                    source['rooms'][0]['attributes']=[dict(type=10,texture=texture),dict(type=1,vertices=[marker,marker,2,3])]
                    city=ImportCity(source).geometry();cap=city.elements[1]
                    self.assertEqual(cap['type'],'sidewalkCap')
                    self.assertEqual(cap['state']['which'],marker+1)
                    self.assertEqual(cap['state']['texture'],'texture/sidewalk.tex' if texture>=0 else '')
                    self.assertEqual(cap['state'].get('invisible',False),texture<0)
                    self.assertEqual(cap['points'],dict(a=city.point_ids[('v',2,None)],b=city.point_ids[('v',3,None)]))

    def test_sidewalk_cap_requires_exact_marker_pair(self):
        for vertices in ([0,1,2,3],[2,2,6,7],[0,0,2,3,6,7]):
            with self.subTest(vertices=vertices):
                source=fixture_psdl();source['rooms'][0]['attributes']=[dict(type=1,vertices=vertices)]
                self.assertEqual(ImportCity(source).geometry().elements[1]['type'],'sidewalkStrip')

    def test_unknown_bounded_path_is_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'props.pathset';write_pathset(p,[dict(type=7,points=[[0,0,0]])])
            city=ImportCity(fixture_psdl()).geometry();city.pathset(read_pathset(p))
            self.assertEqual(len(city.elements),2)
            self.assertIn('omitted',city.warnings[-1]['message'])

    def test_multiroom_rule(self):
        source=fixture_psdl();source['rooms'].append(copy.deepcopy(source['rooms'][0]));source['paths'][0]['rooms']=[1,2]
        city=ImportCity(source).geometry()
        with tempfile.TemporaryDirectory() as tmp:
            defs=Path(tmp)/'defs.csv';rules=Path(tmp)/'rules.csv'
            defs.write_text('name,start,distance,max,min,max,model\na,2,5,30,0,1,test\n')
            rules.write_text('name,p1\nleft,a\nright,a\n')
            import_rules(city,defs,rules)
        prop=city.elements[-1]
        self.assertEqual(prop['type'],'__propPath')
        self.assertEqual(len(prop['points']['ribbons'][0]['segments']),2)
        self.assertTrue(prop['state']['useDistanceReference'])
        self.assertFalse(any('propRule' in e['state'] for e in city.roads.values()))

    def test_single_room_native(self):
        city=ImportCity(fixture_psdl()).geometry()
        with tempfile.TemporaryDirectory() as tmp:
            defs=Path(tmp)/'defs.csv';rules=Path(tmp)/'rules.csv'
            defs.write_text('name,start,distance,max,min,max,model\na,2,5,30,0,1,test\n');rules.write_text('name,p1\nleft,a\nright,a\n')
            import_rules(city,defs,rules)
        self.assertIn('propRule',city.elements[1]['state'])

    def test_inst_reader_and_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.inst';p.write_bytes(struct.pack('<HHB',1,513,0x85)+b'test\0'+struct.pack('<5f',0,-1,2,3,4))
            record=read_inst(p)[0];mapped=instance_transform(record,lambda *args:None)
            self.assertEqual(mapped['position'],[-2,3,4]);self.assertEqual(mapped['settings']['instModifiers'],513)
            self.assertAlmostEqual(mapped['rotation'][1]%360,270)


class Strips(unittest.TestCase):
    def test_native_corners_slopes_and_degenerate(self):
        for raw in (0,1,7,255):
            e,props=export_element([[0,0,0],[0,0,12],[0,0,12],[3,1,14]],raw)
            self.assertIsNotNone(native_strip(e,'main',props,[dict(name='geometry/test.pkg')]))

    def test_fallback(self):
        e,props=export_element([[0,0,0],[0,0,12]])
        for change in ('position','rotation','scale','count','model','spacing'):
            a,b=copy.deepcopy(e),copy.deepcopy(props)
            if change=='position':b[0]['position']=np.add(b[0]['position'],[1,0,0])
            if change=='rotation':b[0]['rotation']=[0,0,0,1]
            if change=='scale':b[0]['scale']=[2,1,1]
            if change=='count':b.pop()
            if change=='model':a['data']['fields']['state']['propRule']['main']['elements'][0]['mesh']='geometry/other.pkg'
            if change=='spacing':a['data']['fields']['state']['propRule']['main']['elements'][0]['rawSpacing']=2.5
            with self.subTest(change=change):self.assertIsNone(native_strip(a,'main',b,[dict(name='geometry/test.pkg')]))

    def test_line_limits_and_phase_rejected(self):
        for fields in (dict(start=1),dict(end=1),dict(maxNumber=10)):
            e,props=export_element([[0,0,0],[0,0,12]])
            entry=e['data']['fields']['state']['propRule']['main']['elements'][0]
            entry.update(type='line',elemDistance=5,**fields)
            self.assertIsNone(native_strip(e,'main',props,[dict(name='geometry/test.pkg')]))


if __name__=='__main__':unittest.main()
