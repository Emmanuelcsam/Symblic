// Trusted finite geometry validator; never candidate mesh construction.
function auditBox(mesh,bounds) {
  function need(ok,why) {if(!ok)throw new Error('Box: '+why);}
  need(mesh&&Object.keys(mesh).sort().join(',')==='triangles,vertices','closed mesh shape');
  const v=mesh.vertices, f=mesh.triangles;
  need(Array.isArray(v)&&v.length===8&&Array.isArray(f)&&f.length===12,'8 vertices / 12 triangles');
  need(v.every(p=>Array.isArray(p)&&p.length===3&&p.every(Number.isFinite)),'finite vertices');
  need(new Set(v.map(JSON.stringify)).size===8,'unique vertices');
  need(v.every(p=>p.every((x,a)=>x===bounds[a][0]||x===bounds[a][1])),'exact bounds/corners');
  const edges=new Map(), area=new Map(), counts=new Map();let volume=0;
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const dot=(a,b)=>a.reduce((sum,x,i)=>sum+x*b[i],0);
  f.forEach((ids,index)=>{
    need(Array.isArray(ids)&&ids.length===3&&new Set(ids).size===3&&ids.every(i=>Number.isInteger(i)&&i>=0&&i<8),'face '+index+' indices');
    const [a,b,c]=ids.map(i=>v[i]);
    const normal=cross(b.map((x,i)=>x-a[i]),c.map((x,i)=>x-a[i]));
    need(dot(normal,normal)>0,'face '+index+' zero area');
    const planes=[];
    for(let axis=0;axis<3;axis++)for(let side=0;side<2;side++)if([a,b,c].every(p=>p[axis]===bounds[axis][side]))planes.push([axis,side]);
    need(planes.length===1,'face '+index+' must lie on one exterior plane');
    const [axis,side]=planes[0],key=axis+','+side;
    need((normal[axis]>0)===Boolean(side)&&normal.every((x,i)=>i===axis||x===0),'face '+index+' indices '+JSON.stringify(ids)+' normal '+JSON.stringify(normal)+' expected axis '+axis+' sign '+(side?'+':'-'));
    area.set(key,(area.get(key)||0)+Math.abs(normal[axis])/2);counts.set(key,(counts.get(key)||0)+1);
    volume+=dot(a,cross(b,c))/6;
    for(let i=0;i<3;i++) {const x=ids[i],y=ids[(i+1)%3],key=Math.min(x,y)+','+Math.max(x,y);if(!edges.has(key))edges.set(key,[]);edges.get(key).push([x,y]);}
  });
  need(edges.size===18&&Array.from(edges.values()).every(e=>e.length===2&&e[0][0]===e[1][1]&&e[0][1]===e[1][0]),'opposite paired edge incidences');
  for(let axis=0;axis<3;axis++)for(let side=0;side<2;side++) {
    const expected=bounds.reduce((product,pair,i)=>i===axis?product:product*(pair[1]-pair[0]),1),key=axis+','+side;
    need(counts.get(key)===2&&Math.abs(area.get(key)-expected)<1e-8,'surface coverage '+key);
  }
  const expected=bounds.reduce((product,pair)=>product*(pair[1]-pair[0]),1);
  need(volume>0&&Math.abs(volume-expected)<1e-7,'positive expected volume');return true;
}
function auditGantry(value,p,travel) {
  function need(ok,why){if(!ok)throw new Error('Gantry: '+why);}
  const w=p.width,d=p.depth,h=p.height,t=p.thickness,cw=p.carriageWidth,cd=p.carriageDepth,ch=p.carriageHeight,g=p.clearance;
  const expected=[
    ['base',[[-w/2,w/2],[-d/2,d/2],[0,t]]],
    ['left_post',[[-w/2,-w/2+t],[-t/2,t/2],[t,h-t]]],
    ['right_post',[[w/2-t,w/2],[-t/2,t/2],[t,h-t]]],
    ['crossbar',[[-w/2,w/2],[-t/2,t/2],[h-t,h]]],
    ['carriage',[[travel-cw/2,travel+cw/2],[-cd/2,cd/2],[h+g,h+g+ch]]]
  ];
  need(value&&Object.keys(value).sort().join(',')==='parts,units'&&value.units==='mm','closed assembly shape / mm');
  need(Array.isArray(value.parts)&&value.parts.length===5,'five separate parts');
  value.parts.forEach((part,i)=>{
    need(part&&Object.keys(part).sort().join(',')==='mesh,name','part '+i+' must have exactly keys name and mesh; observed '+JSON.stringify(Object.keys(part||{})));
    need(part.name===expected[i][0],'part '+i+' must be named '+expected[i][0]);
    need(part.mesh&&!Array.isArray(part.mesh)&&Object.keys(part.mesh).sort().join(',')==='triangles,vertices','part '+i+' mesh must be the whole object {vertices,triangles}, not an array; keep triangles INSIDE mesh');
    auditBox(part.mesh,expected[i][1]);
  });
  for(let i=0;i<5;i++)for(let j=i+1;j<5;j++)need(expected[i][1].some((pair,a)=>Math.min(pair[1],expected[j][1][a][1])-Math.max(pair[0],expected[j][1][a][0])<=0),'no interpenetration '+i+'/'+j);
  need(Math.abs(travel)<=(w-cw)/2,'allowed travel');
  need(expected[4][1][2][0]-expected[3][1][2][1]===g,'clearance');return true;
}
