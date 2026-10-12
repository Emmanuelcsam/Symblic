"""Trusted exact geometry/STL checks for finite synthetic box-part assemblies."""
from collections import Counter,defaultdict
from fractions import Fraction as F
import itertools
import math
import struct

def need(ok,why):
    if not ok:raise ValueError(why)

def vector(a,b):return [y-x for x,y in zip(a,b)]
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def dot(a,b):return sum(x*y for x,y in zip(a,b))

def validate_box(mesh,bounds):
    need(isinstance(mesh,dict) and set(mesh)=={'vertices','triangles'},'mesh closed shape')
    vertices,faces=mesh['vertices'],mesh['triangles']
    need(isinstance(vertices,list) and len(vertices)==8 and isinstance(faces,list) and len(faces)==12,'8 vertices / 12 triangles')
    need(all(isinstance(v,list) and len(v)==3 and all(type(x) in (int,float) and math.isfinite(x) for x in v) for v in vertices),'finite 3D vertices')
    vertices=[tuple(F(str(x)) for x in v) for v in vertices]
    bounds=[[F(str(x)) for x in pair] for pair in bounds]
    corners=set(itertools.product(*bounds))
    need(len(corners)==8 and set(vertices)==corners,'exact corner set and bounds')
    edges=defaultdict(list);surface_area=defaultdict(F);counts=Counter();volume=F(0)
    for index,face in enumerate(faces):
        need(isinstance(face,list) and len(face)==3 and all(type(i) is int and 0<=i<8 for i in face) and len(set(face))==3,'face '+str(index)+' indices')
        a,b,c=[vertices[i] for i in face]
        normal=cross(vector(a,b),vector(a,c));length2=dot(normal,normal)
        need(length2>0,'zero area face '+str(index))
        planes=[(axis,side) for axis in range(3) for side in range(2) if all(v[axis]==bounds[axis][side] for v in (a,b,c))]
        need(len(planes)==1,'face '+str(index)+' is not on one exterior plane')
        axis,side=planes[0]
        need((normal[axis]>0)==bool(side) and all(normal[j]==0 for j in range(3) if j!=axis),'face '+str(index)+' '+str(face)+' normal '+str(normal)+' points inward on '+str(planes[0]))
        surface_area[planes[0]]+=abs(normal[axis])/2;counts[planes[0]]+=1
        volume+=dot(a,cross(b,c))/6
        for i,j in zip(face,face[1:]+face[:1]):edges[tuple(sorted((i,j)))].append((i,j))
    need(len(edges)==18 and all(len(e)==2 and e[0]==e[1][::-1] for e in edges.values()),'opposite paired edge incidences')
    for axis in range(3):
        expected=math.prod(bounds[j][1]-bounds[j][0] for j in range(3) if j!=axis)
        for side in range(2):need(counts[axis,side]==2 and surface_area[axis,side]==expected,'face coverage')
    expected_volume=math.prod(hi-lo for lo,hi in bounds)
    need(volume==expected_volume and volume>0,'exact positive volume')
    return {'passed':True,'vertices':8,'triangles':12,'volume_mm3':float(volume),'bounds_mm':[[float(x) for x in pair] for pair in bounds]}

def expected_parts(p,travel):
    w,d,h,t,cw,cd,ch,gap=[p[k] for k in ('width','depth','height','thickness','carriageWidth','carriageDepth','carriageHeight','clearance')]
    return {
      'base':[[-w/2,w/2],[-d/2,d/2],[0,t]],
      'left_post':[[-w/2,-w/2+t],[-t/2,t/2],[t,h-t]],
      'right_post':[[w/2-t,w/2],[-t/2,t/2],[t,h-t]],
      'crossbar':[[-w/2,w/2],[-t/2,t/2],[h-t,h]],
      'carriage':[[travel-cw/2,travel+cw/2],[-cd/2,cd/2],[h+gap,h+gap+ch]]}

def validate(assembly,p,travel):
    need(isinstance(assembly,dict) and set(assembly)=={'units','parts'} and assembly['units']=='mm','assembly closed shape and millimeters')
    want=expected_parts(p,travel);parts=assembly['parts']
    need(isinstance(parts,list) and len(parts)==5,'five separate parts')
    need(all(isinstance(part,dict) and set(part)=={'name','mesh'} for part in parts),'part closed shape')
    need([part['name'] for part in parts]==list(want),'exact part names/order')
    rows={part['name']:validate_box(part['mesh'],want[part['name']]) for part in parts}
    for (a,ba),(b,bb) in itertools.combinations(want.items(),2):
        need(any(min(ba[i][1],bb[i][1])-max(ba[i][0],bb[i][0])<=0 for i in range(3)),'interpenetrating parts '+a+' / '+b)
    need(abs(travel)<=((p['width']-p['carriageWidth'])/2),'carriage travel bound')
    need(want['carriage'][2][0]-want['crossbar'][2][1]==p['clearance'],'vertical geometric clearance')
    return {'passed':True,'parts':rows,'travel_mm':travel,'clearance_mm':p['clearance'],'total_material_volume_mm3':sum(row['volume_mm3'] for row in rows.values()),'scope':'Geometric mock-up only; no bearing, connection, load, fabrication or control validation'}

def encode_stl(mesh,bounds):
    validate_box(mesh,bounds)
    raw=bytearray(b'Synthetic checked gantry box; coordinates in millimeters'.ljust(80,b'\0'))
    raw.extend(struct.pack('<I',len(mesh['triangles'])))
    for face in mesh['triangles']:
        points=[mesh['vertices'][i] for i in face]
        normal=cross(vector(points[0],points[1]),vector(points[0],points[2]))
        norm=math.sqrt(dot(normal,normal));normal=[x/norm for x in normal]
        raw.extend(struct.pack('<12fH',*normal,*(x for point in points for x in point),0))
    verify_stl(bytes(raw),mesh,bounds)
    return bytes(raw)

def verify_stl(raw,mesh,bounds):
    count=struct.unpack_from('<I',raw,80)[0]
    need(count==12 and len(raw)==84+50*count,'STL count/length')
    vertices=[];faces=[]
    for index,face in enumerate(mesh['triangles']):
        values=struct.unpack_from('<12fH',raw,84+50*index)
        points=[list(values[j:j+3]) for j in (3,6,9)]
        need(points==[mesh['vertices'][i] for i in face],'STL changed model coordinates')
        normal=cross(vector(points[0],points[1]),vector(points[0],points[2]))
        norm=math.sqrt(dot(normal,normal))
        need(list(values[:3])==[x/norm for x in normal] and values[-1]==0,'STL normal/attributes')
        ids=[]
        for point in points:
            if point not in vertices:vertices.append(point)
            ids.append(vertices.index(point))
        faces.append(ids)
    return validate_box({'vertices':vertices,'triangles':faces},bounds)
