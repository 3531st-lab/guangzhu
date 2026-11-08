// Standard architectural views in the same metre-based world coordinates as the model.
// X is east, Y is height, and -Z is north. Projection changes never rescale geometry.
export function normalizeView(value) {
  if (value === true) return 'top';
  if (!value || value === 'isometric') return 'iso';
  return ['iso','top','north','east','south','west','front','back','left','right','selected'].includes(value) ? value : 'iso';
}

export function viewDirection(T, value, roof, frontEdge = 0) {
  const view=normalizeView(value);
  const directions={iso:[1,1,1],top:[0,1,1e-8],north:[0,0,-1],east:[1,0,0],south:[0,0,1],west:[-1,0,0]};
  if (directions[view]) return new T.Vector3(...directions[view]).normalize();
  const outline=roof.outline,a=outline[frontEdge] ?? outline[0],b=outline[(frontEdge+1)%outline.length] ?? outline[1];
  const length=Math.hypot(b[0]-a[0],b[1]-a[1]) || 1;
  const area=outline.reduce((sum,p,i)=>sum+p[0]*outline[(i+1)%outline.length][1]-outline[(i+1)%outline.length][0]*p[1],0);
  const sign=area>=0?1:-1,normal=[sign*(b[1]-a[1])/length,sign*(b[0]-a[0])/length];
  const vector=view==='back'?[-normal[0],0,-normal[1]]:view==='left'?[-normal[1],0,normal[0]]:
    view==='right'?[normal[1],0,-normal[0]]:[normal[0],0,normal[1]];
  return new T.Vector3(...vector).normalize();
}

export function sceneFramePoints(data) {
  const {roof}=data, geometry=data.roof_geometry, points=[];
  const add=point=>{if (point?.length===3 && point.every(Number.isFinite)) points.push(point);};
  for (const p of roof.outline) {
    add(data.world([p[0],p[1],-roof.height_m]));
    add(data.world([p[0],p[1],data.elevation(p)]));
  }
  // Outline vertices alone omit interior ridges, especially in an empty editing preview.
  for (const face of geometry?.faces ?? []) for (const p of face.points ?? []) add(data.world(p));
  for (const p of geometry?.boundary ?? []) add(data.world(p));
  if (Object.prototype.hasOwnProperty.call(geometry ?? {},'parapets')) {
    for (const face of geometry.parapets) for (const p of face) add(data.world(p));
  } else for (const p of roof.outline) add(data.world([p[0],p[1],data.elevation(p)+(roof.parapet_height_m ?? 0)]));
  // Eight extrema enclose every panel without feeding huge arrays into camera fitting.
  if (data.modules.length) {
    const low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity];
    for (const module of data.modules) for (const p of module.points) for(let axis=0;axis<3;axis++) {
      low[axis]=Math.min(low[axis],p[axis]);high[axis]=Math.max(high[axis],p[axis]);
    }
    for(const x of [low[0],high[0]]) for(const y of [low[1],high[1]]) for(const z of [low[2],high[2]]) add([x,y,z]);
  }
  for (const obstacle of roof.obstacles ?? []) {
    const base=geometry?.obstacle_bases?.[obstacle.id] ?? 0;
    const footprint=obstacle.footprint ?? (obstacle.center ? [[obstacle.center[0]-obstacle.radius_m,obstacle.center[1]-obstacle.radius_m],
      [obstacle.center[0]+obstacle.radius_m,obstacle.center[1]+obstacle.radius_m]] : []);
    for (const p of footprint) add(data.world([p[0],p[1],obstacle.height_m+base+(roof.type==='metal'?data.elevation(p):0)]));
  }
  return points;
}

export function resizeCamera(camera, width, height) {
  const aspect=width/height;
  if (camera.isOrthographicCamera) {
    const half=(camera.top-camera.bottom)/2;
    camera.left=-half*aspect;camera.right=half*aspect;
  } else camera.aspect=aspect;
  camera.updateProjectionMatrix();
}

export function fitCamera(T,camera,controls,input,direction,margin=.86) {
  if (!input.length) return;
  const damping=controls.enableDamping;controls.enableDamping=false;controls.update();controls.enableDamping=damping;
  const points=input.map(p=>p.isVector3?p:new T.Vector3(...p));
  const box=new T.Box3().setFromPoints(points),target=box.getCenter(new T.Vector3()),unit=direction.clone().normalize();
  const size=Math.max(box.getSize(new T.Vector3()).length(),1);
  camera.position.copy(target).addScaledVector(unit,size*2);camera.lookAt(target);camera.updateMatrixWorld();
  const right=new T.Vector3().setFromMatrixColumn(camera.matrixWorld,0),up=new T.Vector3().setFromMatrixColumn(camera.matrixWorld,1);
  const projected=points.map(p=>{const relative=p.clone().sub(target);return [relative.dot(right),relative.dot(up),relative.dot(unit)];});
  const aspect=camera.isOrthographicCamera?(camera.right-camera.left)/(camera.top-camera.bottom):camera.aspect;
  let distance=size*2;
  if (camera.isOrthographicCamera) {
    const half=projected.reduce((maximum,[x,y])=>Math.max(maximum,Math.abs(y),Math.abs(x)/aspect),.1)/margin;
    camera.top=half;camera.bottom=-half;camera.left=-half*aspect;camera.right=half*aspect;camera.zoom=1;
  } else {
    camera.zoom=1;
    const tangent=Math.tan(camera.fov*Math.PI/360);
    distance=projected.reduce((maximum,[x,y,z])=>Math.max(maximum,z+Math.max(Math.abs(x)/(tangent*aspect*margin),Math.abs(y)/(tangent*margin))),.1)+size*.015;
  }
  camera.near=Math.max(.01,size*.00001);camera.far=Math.max(size*30,distance+size*5);
  camera.position.copy(target).addScaledVector(unit,distance);camera.lookAt(target);camera.updateProjectionMatrix();
  controls.target.copy(target);controls.minDistance=Math.max(.2,size*.005);controls.maxDistance=Math.max(size*10,distance*2);
  controls.update();camera.updateMatrixWorld();
}

export function changeProjection(T,current,controls,projection) {
  if (!['orthographic','perspective'].includes(projection) || Boolean(current.isOrthographicCamera)===(projection==='orthographic')) return current;
  // Finish an in-flight orbit before handing the same controls to the other camera.
  const damping=controls.enableDamping;controls.enableDamping=false;controls.update();controls.enableDamping=damping;
  const distance=Math.max(.01,current.position.distanceTo(controls.target));
  const direction=current.position.clone().sub(controls.target).normalize();
  let camera;
  if (projection==='orthographic') {
    const half=Math.tan(current.fov*Math.PI/360)*distance/current.zoom;
    camera=new T.OrthographicCamera(-half*current.aspect,half*current.aspect,half,-half,current.near,current.far);
    camera.position.copy(current.position);
  } else {
    const aspect=(current.right-current.left)/(current.top-current.bottom),half=(current.top-current.bottom)/(2*current.zoom);
    camera=new T.PerspectiveCamera(42,aspect,current.near,current.far);
    camera.position.copy(controls.target).addScaledVector(direction,half/Math.tan(camera.fov*Math.PI/360));
  }
  camera.up.copy(current.up);camera.quaternion.copy(current.quaternion);camera.updateProjectionMatrix();camera.updateMatrixWorld();
  camera.far=Math.max(camera.far,camera.position.distanceTo(controls.target)*3);camera.updateProjectionMatrix();
  controls.object=camera;controls.update();camera.updateMatrixWorld();
  return camera;
}
