"""Pure file-to-editable-city mapping; no builder process or filesystem writes."""
import itertools
import math
import numpy as np
from _formats import FormatError


def position(v): return [-float(v[0]), float(v[1]), float(v[2])]


class ImportCity:
    def __init__(self, psdl):
        self.psdl = psdl
        self.points, self.elements, self.warnings = [], [], []
        self.point_ids, self.room_ids, self.roads = {}, {}, {}
        self.prop_paths, self.meshes, self.properties = [], [], {}

    def warn(self, source, message): self.warnings.append(dict(source=source, message=message))

    def point(self, key, value, anchor=None):
        if key not in self.point_ids:
            pid = 'p' + str(len(self.points))
            record = dict(id=pid, position=list(map(float, value)))
            if anchor: record['anchor'] = anchor
            self.points.append(record)
            self.point_ids[key] = pid
        return self.point_ids[key]

    def vertex(self, index, height=None):
        v = position(self.psdl['vertices'][index])
        if height is not None: v[1] = self.height(height)
        return self.point(('v', index, height), v)

    def height(self, index):
        if not 0 <= index < len(self.psdl['heights']): raise FormatError(f'invalid height reference {index}')
        return self.psdl['heights'][index]

    def texture(self, index):
        if index == -1: return ''
        if not 0 <= index < len(self.psdl['textures']): raise FormatError(f'invalid texture reference {index}')
        value = self.psdl['textures'][index]
        return 'texture/' + value + ('' if value.lower().endswith(('.tex', '.tga', '.bmp', '.jpg', '.png')) else '.tex')

    def element(self, typ, name, state=None, points=None, container=None, mesh=None):
        e = dict(id='e'+str(len(self.elements)), type=typ, name=name, state=state or {})
        if points is not None: e['points'] = points
        if container is not None: e['container'] = container
        if mesh is not None: e['mesh'] = mesh
        self.elements.append(e)
        return e

    def geometry(self, room_ids=None):
        for i, room in enumerate(self.psdl['rooms'], 1):
            if room_ids is not None and i not in room_ids:continue
            r = self.element('room', f'Imported room {i}', dict(echo=bool(room['flags'] & 2), warp=bool(room['flags'] & 64), simplifyPerimeter=False),
                             dict(perimeter=[self.vertex(v) for v, neighbor in room['perimeter']]))
            self.room_ids[i] = r['id']
            if room['flags'] & 0x21: self.warn(f'room {i}', 'unrepresented room flags are regenerated')
            tex, last_bound, pending = -1, None, []
            for ai, a in enumerate(room['attributes']):
                typ, vs = a['type'], a.get('vertices', [])
                name = f'Imported room {i} attribute {ai}'
                if typ == 10:
                    tex = a['texture']; continue
                state = dict(texture=self.texture(tex))
                if tex<0:state['invisible']=True
                e = None
                if typ in (0, 1, 2, 8):
                    names = {0: ['leftSidewalk','leftRoad','rightRoad','rightSidewalk'], 1: ['outer','inner'],
                             2: ['left','right'], 8: ['leftSidewalk','leftRoad','leftDivider','rightDivider','rightRoad','rightSidewalk']}[typ]
                    if len(vs) < 2*len(names):
                        self.warn(name, 'degenerate strip omitted'); continue
                    sections = [dict(zip(names, [self.vertex(v) for v in vs[k:k+len(names)]])) for k in range(0,len(vs),len(names))]
                    if typ in (0, 8): state.update(sidewalkTexture=self.texture(tex+1) if tex>=0 else '', lodTexture=self.texture(tex+2) if tex>=0 else '', noCoplanarFix=True)
                    if typ == 2: state.update(style=0, noCoplanarFix=True)
                    if typ == 8:
                        packed, value = a['values']; flags, dt = packed & 255, (packed >> 8)-1
                        state.update(dividerType=flags & 3, dividerValue=value/256, closeStart=bool(flags & 64), closeEnd=bool(flags & 128))
                        for offset,key in enumerate(('dividerSideTexture','dividerFlatTexture','dividerTopTexture','dividerCapTexture')):
                            state[key] = self.texture(dt+offset) if dt >= 0 else ''
                    if typ == 1: state['texture'] = self.texture(tex+1) if tex>=0 else ''
                    e = self.element({0:'roadWithSidewalks',1:'sidewalkStrip',2:'roadWithoutSidewalks',8:'dividedRoad'}[typ],name,state,dict(sections=sections),r['id'])
                    if typ in (0,2,8):
                        self.roads[(i,ai)] = e
                        for tunnel in pending: tunnel['state']['road'] = dict(kind='lowLevel',id=e['id'])
                        pending.clear()
                elif typ in (5,6,12):
                    ids = [self.vertex(v,a['height'] if typ == 12 else None) for v in vs]
                    vertices = [self.points[int(p[1:])]['position'] for p in ids]
                    # Mirroring X reverses winding once. Do not flip individual faces upward: stock
                    # fans include small backward-facing triangles, and flipping those breaks fan topology.
                    triangles = [k for j in range(1,len(ids)-1) for k in (0,j+1,j)]
                    # Stock fans can repeat a perimeter vertex, yielding zero-area faces. Preserve their
                    # surface, but do not feed degenerate topology to the exporter's fan reconstruction.
                    unique=list(dict.fromkeys(ids))
                    remap=[unique.index(pid) for pid in ids]
                    clean=[]
                    for j in range(0,len(triangles),3):
                        tri=[remap[k] for k in triangles[j:j+3]]
                        a0,b0,c0=[np.asarray(self.points[int(unique[k][1:])]['position']) for k in tri]
                        if len(set(tri))==3 and np.linalg.norm(np.cross(b0-a0,c0-a0))>1e-9:clean.extend(tri)
                    ids,triangles=unique,clean
                    if not triangles:
                        self.warn(name,'zero-area fan omitted');continue
                    flat = max(v[1] for v in vertices)-min(v[1] for v in vertices) < 0.05
                    target = 'roofTriangleFan' if typ == 12 else 'roadTriangleFan' if typ == 5 and flat else 'triangleFan'
                    if typ == 5 and not flat: self.warn(name,'non-flat culled fan retains geometry but loses camera culling')
                    e = self.element(target,name,state,container=r['id'],mesh=dict(vertices=ids,triangles=triangles))
                elif typ == 4:
                    if len(vs) != 4: raise FormatError(f'{name}: crosswalk needs four vertices')
                    state['texture'] = self.texture(tex+2) if tex>=0 else ''
                    e = self.element('crosswalk',name,state,{'p'+str(j+1):self.vertex(v) for j,v in enumerate(vs)},r['id'])
                elif typ in (3,7,11):
                    vals = a['values']; top = vals[1] if typ in (7,11) else vals[0]
                    corners = dict(bottomLeft=self.vertex(vs[0],vals[0] if typ == 11 else None),
                                   bottomRight=self.vertex(vs[1],vals[0] if typ == 11 else None),
                                   topLeft=self.vertex(vs[0],top),topRight=self.vertex(vs[1],top))
                    for bottom,upper in (('bottomLeft','topLeft'),('bottomRight','topRight')):
                        pid = corners[upper]
                        if pid != corners[bottom]: self.points[int(pid[1:])]['anchor'] = dict(column=corners[bottom])
                    if typ == 7: state = dict(bothSides=False, invisible=tex<0)
                    if typ == 3: state['textureScale'] = self.height(vals[1])
                    if typ == 11:
                        state.update(uRepeat=vals[2],vRepeat=vals[3])
                        if last_bound: state['bound'] = dict(kind='lowLevel',id=last_bound)
                    e = self.element({3:'sliver',7:'facadeBound',11:'facade'}[typ],name,state,corners,r['id'])
                    if typ == 7: last_bound=e['id']
                elif typ == 9:
                    vals = a['values']
                    if len(vals) not in (2,3,9,10): self.warn(name,'unsupported tunnel payload omitted'); continue
                    flags=vals[0]
                    keys = {1:'leftSide',2:'rightSide',4:'wall',8:'flatCeiling',16:'closedStartLeft',32:'closedEndLeft',64:'closedStartRight',128:'closedEndRight',256:'curvedCeiling',512:'offsetStartLeft',1024:'offsetEndLeft',2048:'offsetStartRight',4096:'offsetEndRight',8192:'curvedSides',16384:'culled'}
                    state={key:bool(flags & bit) for bit,key in keys.items()}
                    state['height']=vals[1]/256
                    if tex<0:state['invisible']=True
                    for j in range(6): state['texture'+str(j)]=self.texture(tex+j) if tex>=0 else ''
                    if len(vals)<9:
                        e=self.element('roadTunnel',name,state,container=r['id']);pending.append(e)
                    else:
                        base=2 if len(vals)==9 else 3
                        bits=vals[base+1] | (vals[base+2]<<16)
                        per=room['perimeter'];walls=[]
                        for j in range(len(per)):
                            if bits & (1 << ((j+1)%len(per))): walls.append(dict(points=[self.vertex(per[j][0]),self.vertex(per[(j+1)%len(per)][0])]))
                        for key in ('leftSide','rightSide'):state.pop(key,None)
                        e=self.element('junctionTunnel',name,state,dict(walls=walls),r['id'])
                        self.warn(name,'junction tunnel fan origin and per-edge offsets are regenerated')
            if pending: self.warn(f'room {i}','road tunnel without following road')
        return self

    def bai(self, bai):
        intersections={}
        for it in bai['intersections']:
            if it['room'] not in self.room_ids: raise FormatError('BAI intersection has invalid room')
            p=self.point(('baiIntersection',it['id']),position(it['center']))
            e=self.element('baiIntersection',f'Imported BAI intersection {it["id"]}',{},dict(center=p),self.room_ids[it['room']])
            intersections[it['id']]=e['id']
        for rd in bai['roads']:
            if rd['flags'] & ~7:self.warn(f'BAI road {rd["id"]}','unsupported road flags omitted')
            room=next((r for r in rd['rooms'] if r in self.room_ids),None)
            if room is None: raise FormatError(f'BAI road {rd["id"]}: no valid room')
            state=dict(autoCalculated=False,divided=bool(rd['flags']&1),freeway=bool(rd['flags']&4),alley=bool(rd['flags']&2))
            a,b=rd['right'],rd['left']
            # Search existing generic flags for the exact permissions while retaining lane geometry.
            matches=[]
            for lp,rp,geo,alley in itertools.product((False,True),repeat=4):
                ped=lp or rp;traffic=(a['lanes']+b['lanes']>0) and not alley
                t=0 if ped and traffic else 1 if ped else 2 if traffic else 3
                def ambient(n,p): return (1 if t==0 or (t==1 and p) else 3) if n==0 else (2 if t==0 and (not p or not geo) else t)
                # The exporter's colon-separated sidewalk flags use builder sides, opposite the file sides.
                out=(ambient(a['lanes'],lp),ambient(b['lanes'],rp))
                wanted=(a['ambient'],b['ambient'])
                perms=lambda value: ({0,2}.__contains__(value),{0,1}.__contains__(value))
                penalty=sum(100 if got and not want else 1 if want and not got else 0 for x,y in zip(out,wanted) for got,want in zip(perms(x),perms(y)))
                matches.append((penalty,int(alley!=bool(rd['flags']&2)),lp,rp,geo,alley))
            penalty,_,lp,rp,geo,alley=min(matches)
            state.update(noLeftPedestrians=not lp,noRightPedestrians=not rp,geoSidewalks=geo,alley=alley)
            if penalty:self.warn(f'BAI road {rd["id"]}','ambient permissions approximated')
            for end in ('start','end'):
                state[end+'Rule']=rd[end]['rule']
                iid=rd[end]['intersection']
                if iid != 0xcdcdcdcd:
                    if iid not in intersections: raise FormatError('invalid BAI intersection reference')
                    state[end+'Intersection']=dict(kind='lowLevel',id=intersections[iid])
            sections=[]
            for j in range(rd['n']):
                def p(key,v):return self.point(('bai',rd['id'],j,key),position(v))
                sections.append(dict(rightEdge=p('re',a['outer'][j]),rightCurb=p('rc',a['inner'][j]),
                    backwardLanes=[p('b'+str(k),lane[rd['n']-1-j]) for k,lane in reversed(list(enumerate(a['laneVertices'])))],
                    forwardLanes=[p('f'+str(k),lane[j]) for k,lane in enumerate(b['laneVertices'])],
                    leftCurb=p('lc',b['inner'][j]),leftEdge=p('le',b['outer'][j])))
            if a['trams'] or b['trams']:
                offsets=[]
                for side in ('right','left'):
                    for rail in rd[side]['tramVertices']:
                        samples=list(reversed(rail)) if side=='right' else rail
                        offsets.extend(abs(float(np.dot(np.subtract(v,c),x))) for v,c,x in zip(samples,rd['center'],rd['x']))
                offset=float(np.median(offsets)) if offsets else 2.5
                state.update(cableCar=True,cableCarOffset=offset if offset>0 else 2.5)
                self.warn(f'BAI road {rd["id"]}','tram splines regenerated symmetrically from their measured offset')
            if a['trains'] or b['trains']:self.warn(f'BAI road {rd["id"]}','BAI train splines omitted; race train paths are separate')
            if len(rd['rooms'])>1:self.warn(f'BAI road {rd["id"]}','additional room memberships omitted')
            self.element('baiRoad',f'Imported BAI road {rd["id"]}',state,dict(sections=sections),self.room_ids[room])
        self.warn('BAI','distances, frames, per-route speed, traffic lights, sidewalks, intersection ordering and culling are regenerated')

    def pathset(self, paths):
        for i,path in enumerate(paths):
            if path['type'] not in (0,1,2):
                self.warn(f'props path {i}',f'unsupported bounded path type {path["type"]} omitted');continue
            model='geometry/'+path['name']+'.pkg'
            if path['type']==2:
                if len(path['points'])<2:self.warn(f'props path {i}','strip with fewer than two points omitted');continue
                sections=[]
                for j,v in enumerate(path['points']):
                    pid=self.point(('pathset',i,j),position(v))
                    sections.append(dict(start=pid,end=pid,reference=pid))
                rule=dict(main=dict(type='pathsetStrip',elements=[dict(type='pathsetStrip',mesh=model,rawSpacing=path['spacing'])]))
                self.element('__propPath',f'Imported prop strip {i}',dict(ribbonNames=['main'],propRule=rule),
                             dict(ribbons=[dict(segments=[dict(sections=sections)])]))
            else:
                step=2 if path['type']==1 else 1
                for j in range(0,len(path['points']),step):
                    pos=position(path['points'][j]);yaw=0
                    if step==2:
                        d=np.subtract(position(path['points'][j+1]),pos)
                        yaw=math.degrees(math.atan2(d[2],-d[0]))
                    self.meshes.append(dict(mesh=model,position=pos,rotation=[0,yaw,0],settings=dict(prop=True)))

    def payload(self): return dict(points=self.points,elements=self.elements)
