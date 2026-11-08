import {panelMatrix} from './scene-data.js';
import {moduleSurface,surfaceFrame,transformModuleGeometry,snapModuleMove,snapModuleAngle,lockedRegionSegments} from './module-transform-geometry.js';

// This controller owns only temporary annotations. The server remains responsible
// for collision, boundary and lock validation before a candidate can be saved.
export function createModuleTransform(T,{canvas,scene,controls,getCamera,getPanels,getModelMeshes,onTransform,onStatus,onSelect}) {
  let data=null,config={enabled:false,mode:'off',selectedIds:[],lockedIds:[],snap:{}},drag=null,disposed=false;
  let handles=null,ghost=null,original=null,guides=null,lockedRegions=null,handleInfo=null,suppressUntil=0,lastText='';
  const layer=new T.Group();layer.name='module-transform';scene.add(layer);
  const raycaster=new T.Raycaster(),pointer=new T.Vector2();
  const world=p=>new T.Vector3(...data.world(p));
  const raw=p=>[p.x+data.center[0],data.center[1]-p.z,p.y-data.roof.height_m];
  const vector=p=>new T.Vector3(p[0],p[2],-p[1]);
  const linear=color=>new T.Color(color).convertSRGBToLinear();
  function release(object) {
    if (!object) return;
    object.traverse(child=>{child.geometry?.dispose();for(const material of Array.isArray(child.material)?child.material:[child.material])material?.dispose();});
    layer.remove(object);
  }
  function clearGhost() {release(ghost);release(original);release(guides);ghost=original=guides=null;}
  function showLockedRegions() {
    release(lockedRegions);lockedRegions=null;
    if(!data||!config.enabled)return;
    const segments=(data.design.locked_regions ?? []).flatMap(region=>lockedRegionSegments(data.roof,region.polygon));
    if(!segments.length)return;
    const points=segments.flat().map(point=>world([point[0],point[1],point[2]+.08]));
    lockedRegions=new T.LineSegments(new T.BufferGeometry().setFromPoints(points),
      new T.LineDashedMaterial({color:linear('#dba63b'),dashSize:.24,gapSize:.14,depthTest:false,depthWrite:false}));
    lockedRegions.computeLineDistances();lockedRegions.renderOrder=21;lockedRegions.userData.moduleTransform='locked-regions';layer.add(lockedRegions);
  }
  function status(text,dragging=Boolean(drag)) {lastText=text;onStatus?.({text,dragging});}
  function selected() {
    const ids=new Set(config.selectedIds),rows=(data?.modules ?? []).filter(module=>ids.has(module.id));
    return rows.length===ids.size?rows:[];
  }
  function blocked() {
    if (!config.enabled||!['move','rotate'].includes(config.mode)) return '';
    const spec=data?.module_transform_spec;
    if (!spec?.available || ![spec.length_m,spec.width_m].every(value=>Number.isFinite(value)&&value>0)
      || ![spec.gap_m,spec.lower_edge_m].every(value=>Number.isFinite(value)&&value>=0))
      return spec?.reason ?? '此记录缺少精确组件参数，暂不能三维拖拽';
    if (data.edit_preview) return '先确认或取消当前候选预览';
    if (config.busy) return '正在校核，请稍候';
    if (selected().some(module=>config.lockedIds.includes(module.id))) return '选中组件已锁定，请先解除相关锁定';
    return '';
  }
  function active() {return !disposed&&data&&config.enabled&&['move','rotate'].includes(config.mode)&&!blocked()&&selected().length>0;}
  function setRay(event) {
    const rect=canvas.getBoundingClientRect();
    if (!rect.width||!rect.height) return false;
    pointer.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);
    const camera=getCamera();camera.updateMatrixWorld();raycaster.setFromCamera(pointer,camera);return true;
  }
  function outline(modules,color,tag) {
    const vertices=modules.flatMap(module=>module.corners.flatMap((point,index)=>[...data.world(point),...data.world(module.corners[(index+1)%4])]));
    const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(vertices,3));
    const object=new T.LineSegments(geometry,new T.LineBasicMaterial({color:linear(color),depthTest:false,depthWrite:false}));
    object.renderOrder=22;object.userData.moduleTransform=tag;layer.add(object);return object;
  }
  function makeHandles() {
    release(handles);handles=null;handleInfo=null;
    if (!active()||drag) return;
    const rows=selected(),first=rows[0],surface=moduleSurface(first,data.roof);
    if (!surface) return;
    const basis=surfaceFrame(surface,data.roof.type==='flat');
    const center=rows.reduce((sum,module)=>sum.map((value,i)=>value+module.center[i]/rows.length),[0,0,0]);
    const normal=vector(basis.normal),position=world(center).addScaledVector(normal,.12);
    const radius=Math.max(.7,...rows.flatMap(module=>module.corners.map(point=>world(point).distanceTo(world(center)))))+.35;
    handles=new T.Group();handles.userData.moduleTransform='handles';
    const material=new T.MeshBasicMaterial({color:linear(config.mode==='rotate'?'#efb33a':'#39cf87'),
      side:T.DoubleSide,depthTest:false,depthWrite:false,transparent:true,opacity:.92});
    const object=new T.Mesh(config.mode==='rotate'?new T.TorusGeometry(radius,Math.min(.09,Math.max(.035,radius*.018)),8,96):new T.PlaneGeometry(.65,.65),material);
    object.position.copy(position);object.quaternion.setFromUnitVectors(new T.Vector3(0,0,1),normal);
    object.renderOrder=25;object.userData.moduleTransformHandle=config.mode;handles.add(object);layer.add(handles);
    handleInfo={position,normal,basis,radius,center,first};
  }
  function restoreControls(session) {if(session)controls.enabled=session.controlsEnabled;}
  function endCapture(session) {
    try {if(canvas.hasPointerCapture?.(session.pointerId))canvas.releasePointerCapture(session.pointerId);} catch {}
  }
  function cancel(text='已取消三维拖拽') {
    if (!drag) return false;
    const session=drag;drag=null;suppressUntil=performance.now()+500;
    restoreControls(session);endCapture(session);canvas.style.cursor='';clearGhost();makeHandles();status(text,false);return true;
  }
  function updateGhost(operation) {
    const modules=drag.modules.map(module=>transformModuleGeometry(module,data.roof,operation,data.module_transform_spec));
    if (modules.some(module=>!module)) return;
    if (!ghost) {
      ghost=new T.Group();ghost.userData.moduleTransform='ghost';layer.add(ghost);
      const panels=new T.InstancedMesh(new T.BoxGeometry(1,1,1),new T.MeshBasicMaterial({color:linear('#39cf87'),
        transparent:true,opacity:.42,depthTest:false,depthWrite:false}),modules.length);
      panels.renderOrder=20;panels.frustumCulled=false;panels.userData.moduleTransform='ghost-panels';ghost.add(panels);
      original=outline(drag.modules,'#e99b34','original');
    }
    const panels=ghost.children[0];
    modules.forEach((module,index)=>panels.setMatrixAt(index,new T.Matrix4().fromArray(panelMatrix({...module,position:data.world(module.center),points:module.corners.map(data.world)}))));
    panels.instanceMatrix.needsUpdate=true;
    const oldOutline=ghost.children[1];
    if (oldOutline) {oldOutline.geometry.dispose();oldOutline.material.dispose();ghost.remove(oldOutline);}
    const border=outline(modules,'#39cf87','new-position');layer.remove(border);ghost.add(border);
    release(guides);guides=null;
    if (operation.guides?.length) {
      const points=operation.guides.flatMap(line=>[data.world(line.from),data.world(line.to)]);
      guides=new T.LineSegments(new T.BufferGeometry().setFromPoints(points.map(point=>new T.Vector3(...point))),
        new T.LineDashedMaterial({color:linear('#efb33a'),dashSize:.12,gapSize:.08,depthTest:false,depthWrite:false}));
      guides.computeLineDistances();guides.renderOrder=23;guides.userData.moduleTransform='snap-guides';layer.add(guides);
    }
  }
  function blockEvent(event) {event.preventDefault();event.stopImmediatePropagation();}
  function down(event) {
    if (disposed||event.button!==0||event.isPrimary===false||drag||!setRay(event)) return;
    scene.updateMatrixWorld(true);
    const panels=getPanels(),meshes=(getModelMeshes?.() ?? [panels]).filter(object=>{
      if (!object) return false;
      for(let parent=object;parent;parent=parent.parent) if (!parent.visible) return false;
      return !object.material || (Array.isArray(object.material)?object.material:[object.material]).some(material=>material.visible&&material.opacity>0);
    });
    const hit=raycaster.intersectObjects(meshes,false)[0],module=hit?.object===panels&&data?.modules[hit.instanceId];
    let selectedHit=module&&config.selectedIds.includes(module.id),autoSelected=false;
    if (config.enabled&&['move','rotate'].includes(config.mode)&&module&&!selectedHit) {
      if (config.lockedIds.includes(module.id)) {blockEvent(event);suppressUntil=performance.now()+500;status('选中组件已锁定，请先解除相关锁定',false);return;}
      if (!blocked()) {
        autoSelected=true;
        onSelect?.(module.id,{source:'3d',extend:Boolean(event.ctrlKey||event.metaKey)});
        if (!config.selectedIds.includes(module.id)) {
          config.selectedIds=(event.ctrlKey||event.metaKey)?[...new Set([...config.selectedIds,module.id])]:[module.id];
          makeHandles();
        }
        selectedHit=config.selectedIds.includes(module.id);
      }
    }
    if (config.enabled&&selectedHit&&blocked()) {blockEvent(event);suppressUntil=performance.now()+500;status(blocked(),false);return;}
    if (!active()||!handleInfo) return;
    const handle=raycaster.intersectObjects(handles.children,true)[0];
    if (!handle&&!(['move','rotate'].includes(config.mode)&&selectedHit)) return;
    const anchor=handle?handleInfo.first:module;
    const surface=moduleSurface(anchor,data.roof),basis=surfaceFrame(surface,data.roof.type==='flat');
    const normal=vector(basis.normal),center=handleInfo.position.clone();
    const plane=new T.Plane().setFromNormalAndCoplanarPoint(normal,config.mode==='rotate'?center:world(anchor.center));
    const start=raycaster.ray.intersectPlane(plane,new T.Vector3());
    if (!start) {status('请转到能看见屋面的视角后拖拽',false);return;}
    blockEvent(event);
    const controlsEnabled=controls.enabled,position=getCamera().position.clone(),target=controls.target.clone(),damping=controls.enableDamping;
    controls.enableDamping=false;controls.update();getCamera().position.copy(position);controls.target.copy(target);controls.update();controls.enableDamping=damping;controls.enabled=false;
    const model=raw(start),relative=start.clone().sub(center);
    const startAngle=Math.atan2(relative.dot(vector(basis.uphill)),relative.dot(vector(basis.right)));
    drag={pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,start:model,plane,center,basis,startAngle,
      anchor,modules:selected().map(module=>({...module})),mode:config.mode,controlsEnabled,moved:false,operation:null,hitId:(handle||autoSelected)?null:module?.id};
    try {canvas.setPointerCapture(event.pointerId);} catch {}
    canvas.style.cursor='grabbing';status(config.mode==='move'?'拖动组件；Alt 临时关闭吸附，Esc 取消':'拖动圆环；各组件绕自身中心旋转，Esc 取消');
  }
  function move(event) {
    if (!drag||event.pointerId!==drag.pointerId) return;
    blockEvent(event);if(!setRay(event))return;
    if (Math.hypot(event.clientX-drag.startX,event.clientY-drag.startY)>3) drag.moved=true;
    if (!drag.moved) return;
    const position=raycaster.ray.intersectPlane(drag.plane,new T.Vector3());if(!position)return;
    let operation;
    if (drag.mode==='move') {
      const point=raw(position),camera=getCamera(),height=canvas.getBoundingClientRect().height;
      const scale=camera.isOrthographicCamera?(camera.top-camera.bottom)/camera.zoom:2*camera.position.distanceTo(controls.target)*Math.tan(camera.fov*Math.PI/360);
      operation={mode:'move',...snapModuleMove(drag.anchor,data.modules,config.selectedIds,data.roof,data.module_transform_spec,
        {dx_m:point[0]-drag.start[0],dy_m:point[1]-drag.start[1]}, {...config.snap,toleranceM:Math.min(.3,Math.max(.025,scale/height*9))},event.altKey)};
    } else {
      const relative=position.clone().sub(drag.center);
      const angle=Math.atan2(relative.dot(vector(drag.basis.uphill)),relative.dot(vector(drag.basis.right)));
      operation={mode:'rotate',...snapModuleAngle((drag.startAngle-angle)*180/Math.PI,config.snap,event.altKey)};
    }
    drag.operation=operation;updateGhost(operation);
    const suffix=operation.snap.applied?({grid:'网格吸附',center:'中心对齐',edge:'边线对齐',gap:`安装间隙 ${data.module_transform_spec.gap_m} m`,angle:'角度吸附'}[operation.snap.kind]):'自由移动';
    status(operation.mode==='move'?`X ${operation.dx_m.toFixed(3)} m · Y ${operation.dy_m.toFixed(3)} m · ${suffix}`:
      `旋转 ${operation.angle_deg.toFixed(1)}° · ${event.altKey?'自由角度':suffix} · 每块绕自身中心`);
  }
  function up(event) {
    if (!drag||event.pointerId!==drag.pointerId) return;
    blockEvent(event);
    const session=drag;drag=null;suppressUntil=performance.now()+500;
    restoreControls(session);endCapture(session);canvas.style.cursor='';clearGhost();makeHandles();
    const operation=session.operation,changed=operation&&(operation.mode==='move'?Math.hypot(operation.dx_m,operation.dy_m)>1e-7:Math.abs(operation.angle_deg)>1e-7);
    if(session.moved&&changed) {
      onTransform?.({mode:operation.mode,module_ids:session.modules.map(module=>module.id),
        ...(operation.mode==='move'?{dx_m:operation.dx_m,dy_m:operation.dy_m}:{angle_deg:operation.angle_deg}),
        snap:{...config.snap,...operation.snap}});
      status('正在请求修改预览…',false);
    } else {
      status(session.moved?'位置未改变，未提交预览':'',false);
      if (!session.moved&&session.hitId) onSelect?.(session.hitId,{source:'3d',extend:Boolean(event.ctrlKey||event.metaKey)});
    }
  }
  const cancelled=event=>{if(drag&&event.pointerId===drag.pointerId){blockEvent(event);cancel();}};
  const lost=event=>{if(drag&&event.pointerId===drag.pointerId)cancel('指针已离开，已取消拖拽');};
  const click=event=>{if(performance.now()<suppressUntil)blockEvent(event);};
  const key=event=>{if(event.key==='Escape'&&drag){blockEvent(event);cancel();}};
  const blur=()=>cancel('窗口失去焦点，已取消拖拽');
  const visibility=()=>{if(document.hidden)cancel('页面已隐藏，已取消拖拽');};
  for(const [name,handler] of [['pointerdown',down],['pointermove',move],['pointerup',up],['pointercancel',cancelled],['lostpointercapture',lost],['click',click]])canvas.addEventListener(name,handler,true);
  window.addEventListener('keydown',key,true);window.addEventListener('blur',blur);document.addEventListener('visibilitychange',visibility);
  return {setData(value){cancel();data=value;clearGhost();showLockedRegions();makeHandles();},
    configure(value={}) {
      const next={...config,...value,mode:value.mode==='view'?'off':value.mode??config.mode,
        selectedIds:[...new Set(value.selectedIds??config.selectedIds)],lockedIds:[...new Set(value.lockedIds??config.lockedIds)],snap:{...config.snap,...value.snap}};
      if(JSON.stringify(next)!==JSON.stringify(config))cancel();config=next;showLockedRegions();makeHandles();
    },cancel,isDragging:()=>Boolean(drag),stats:()=>({enabled:Boolean(active()),mode:config.mode,dragging:Boolean(drag),
      ghostPanels:ghost?.children[0]?.count ?? 0,handles:handles?.children.length ?? 0,lockedRegionSegments:lockedRegions?.geometry.attributes.position.count/2 || 0,
      operation:drag?.operation ?? null,reason:blocked(),text:lastText}),
    dispose(){if(disposed)return;cancel();disposed=true;release(handles);release(lockedRegions);clearGhost();scene.remove(layer);
      for(const [name,handler] of [['pointerdown',down],['pointermove',move],['pointerup',up],['pointercancel',cancelled],['lostpointercapture',lost],['click',click]])canvas.removeEventListener(name,handler,true);
      window.removeEventListener('keydown',key,true);window.removeEventListener('blur',blur);document.removeEventListener('visibilitychange',visibility);
    }};
}
