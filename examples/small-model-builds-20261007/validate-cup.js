// Trusted finite checker only. The model supplies every geometry function.
function auditCup(mesh, width, depth, height, wall, base) {
  function need(ok, message) { if (!ok) throw new Error(message); }
  const iw = width - 2 * wall, id = depth - 2 * wall;
  const tolerance = 1e-8, near = (a,b) => Math.abs(a-b) <= tolerance;
  need(mesh && Object.keys(mesh).sort().join(',') === 'triangles,vertices', 'mesh needs exactly vertices and triangles');
  const vertices = mesh.vertices, faces = mesh.triangles;
  need(Array.isArray(vertices) && vertices.length === 16, 'expected sixteen shared vertices');
  need(Array.isArray(faces) && faces.length === 28, 'expected twenty-eight triangles');
  need(vertices.every(p => Array.isArray(p) && p.length === 3 && p.every(Number.isFinite)), 'finite xyz coordinates required');
  const expectedRings = [[width,depth,0],[width,depth,height],[iw,id,height],[iw,id,base]];
  for (let ring=0; ring<4; ring++) {
    const [w,d,z] = expectedRings[ring];
    const expected = [[-w/2,-d/2,z],[w/2,-d/2,z],[w/2,d/2,z],[-w/2,d/2,z]];
    for (let i=0; i<4; i++) need(vertices[4*ring+i].every((x,j) => near(x,expected[i][j])), 'ring coordinate/order mismatch');
  }
  need(new Set(vertices.map(p => p.join(','))).size === 16, 'vertices must be distinct');
  const edges = new Map(), faceKeys = new Set(), incidence = vertices.map(() => []);
  const counts = {}, areas = {};
  let volume = 0;
  function intersectionArea(points) {
    let polygon = points.map(p => p.slice(0,2));
    for (const [axis,bound,sign] of [[0,-iw/2,1],[0,iw/2,-1],[1,-id/2,1],[1,id/2,-1]]) {
      const next = [];
      for (let i=0; i<polygon.length; i++) {
        const a=polygon[i], b=polygon[(i+1)%polygon.length];
        const insideA=sign*(a[axis]-bound)>=0, insideB=sign*(b[axis]-bound)>=0;
        if (insideA) next.push(a);
        if (insideA !== insideB) {
          const t=(bound-a[axis])/(b[axis]-a[axis]);
          next.push(a.map((x,k) => x+t*(b[k]-x)));
        }
      }
      polygon = next;
    }
    return Math.abs(polygon.reduce((sum,p,i) => {
      const q=polygon[(i+1)%polygon.length]; return sum+p[0]*q[1]-p[1]*q[0];
    },0))/2;
  }
  for (let fi=0; fi<faces.length; fi++) {
    const face=faces[fi];
    need(Array.isArray(face) && face.length===3 && face.every(i => Number.isInteger(i) && i>=0 && i<16), 'triangle index range');
    need(new Set(face).size===3, 'repeated vertex in triangle');
    const key=[...face].sort((a,b)=>a-b).join(',');
    need(!faceKeys.has(key), 'duplicate geometric triangle'); faceKeys.add(key);
    const [a,b,c]=face.map(i=>vertices[i]);
    const u=b.map((x,i)=>x-a[i]), v=c.map((x,i)=>x-a[i]);
    const n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];
    const area=Math.hypot(...n)/2;
    need(area>tolerance, 'zero-area triangle');
    const points=[a,b,c], plane=(axis,value)=>points.every(p=>near(p[axis],value));
    let category=null, direction=null;
    if (plane(2,0)) { category='bottom'; direction=[0,0,-1]; }
    else if (plane(2,height)) {
      category='rim'; direction=[0,0,1];
      need(intersectionArea(points)<tolerance, 'face '+fi+' indices '+JSON.stringify(face)+' at z='+height+' crosses the opening; rim must stay outside the inner rectangle');
    } else if (plane(2,base) && points.every(p=>Math.abs(p[0])<=iw/2+tolerance && Math.abs(p[1])<=id/2+tolerance)) {
      category='floor'; direction=[0,0,1];
    } else {
      for (const [axis,outer,inner] of [[0,width/2,iw/2],[1,depth/2,id/2]]) {
        for (const sign of [-1,1]) {
          if (plane(axis,sign*outer)) { category='outer'+axis+':'+sign; direction=[0,0,0]; direction[axis]=sign; }
          if (plane(axis,sign*inner) && points.every(p=>p[2]>=base-tolerance)) {
            category='inner'+axis+':'+sign; direction=[0,0,0]; direction[axis]=-sign;
          }
        }
      }
    }
    need(category!==null, 'face '+fi+' indices '+JSON.stringify(face)+' coordinates '+JSON.stringify(points)+' is not on a specified material boundary');
    need(n.reduce((sum,x,i)=>sum+x*direction[i],0)>tolerance, 'face '+fi+' indices '+JSON.stringify(face)+' surface '+category+' observed normal '+JSON.stringify(n)+' must point along outward direction '+JSON.stringify(direction)+'; outer bottom is -Z, cavity floor/rim are +Z');
    counts[category]=(counts[category]||0)+1; areas[category]=(areas[category]||0)+area;
    volume += (a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6;
    for (let i=0;i<3;i++) {
      const x=face[i], y=face[(i+1)%3], key=x<y?x+':'+y:y+':'+x;
      const edge=edges.get(key)||{count:0,direction:0,faces:[]};
      edge.count++; edge.direction+=x<y?1:-1; edge.faces.push(fi); edges.set(key,edge);
      incidence[x].push(fi);
    }
  }
  need([...edges.values()].every(e=>e.count===2 && e.direction===0), 'shared edges need two opposite incidences');
  need(edges.size===42 && vertices.length-edges.size+faces.length===2, 'closed genus-zero material boundary expected');
  const visited=new Set([0]), pending=[0];
  while(pending.length) {
    const fi=pending.pop();
    for(const vi of faces[fi]) for(const other of incidence[vi]) if(!visited.has(other)){visited.add(other);pending.push(other);}
  }
  need(visited.size===28, 'mesh must be connected');
  const expectedAreas={bottom:width*depth, floor:iw*id, rim:width*depth-iw*id};
  for(const sign of [-1,1]) {
    expectedAreas['outer0:'+sign]=depth*height; expectedAreas['outer1:'+sign]=width*height;
    expectedAreas['inner0:'+sign]=id*(height-base); expectedAreas['inner1:'+sign]=iw*(height-base);
  }
  for(const [key,area] of Object.entries(expectedAreas)) {
    need(counts[key]===(key==='rim'?8:2), 'boundary triangulation count: '+key);
    need(near(areas[key],area), 'boundary area mismatch: '+key);
  }
  const expectedVolume=width*depth*height-iw*id*(height-base);
  need(volume>0 && Math.abs(volume-expectedVolume)<1e-6, 'positive material volume mismatch');
  return {passed:true, vertices:16, triangles:28, edges:42, volume, expectedVolume,
          outer:[width,depth,height], cavity:[iw,id,height-base], openInterior:true};
}
