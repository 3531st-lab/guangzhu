// Geometry-only editor operations. They return new values so one edit is one undo step.
const finite = value => typeof value === 'number' && Number.isFinite(value);
const clean = value => Math.round(value * 1e9) / 1e9;
const radians = angle => angle * Math.PI / 180;

export function itemCenter(item) {
  return item.center ?? [0, 1].map(axis => item.points.reduce((sum, point) => sum + point[axis], 0) / item.points.length);
}

export function rectangleInfo(points) {
  if (points?.length !== 4) return null;
  const edges = points.map((point, i) => points[(i + 1) % 4].map((value, axis) => value - point[axis]));
  const lengths = edges.map(edge => Math.hypot(...edge));
  if (lengths.some(length => length <= 1e-9) || edges.some((edge, i) =>
    Math.abs(edge[0] * edges[(i + 1) % 4][0] + edge[1] * edges[(i + 1) % 4][1]) > 1e-7 * lengths[i] * lengths[(i + 1) % 4])) return null;
  const [cx, cy] = itemCenter({points});
  return {w:lengths[0], d:lengths[1], turn:Math.atan2(edges[0][1], edges[0][0]) * 180 / Math.PI, cx, cy};
}

export function rectanglePoints({w, d, turn = 0, cx, cy}) {
  if (![w, d, turn, cx, cy].every(finite) || w <= 0 || d <= 0) throw new Error('长宽必须大于0，坐标和角度必须为有效数字');
  const angle = radians(turn), c = Math.cos(angle), s = Math.sin(angle);
  return [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]]
    .map(([x, y]) => [clean(cx + x * c - y * s), clean(cy + x * s + y * c)]);
}

export function moveItem(item, dx, dy) {
  if (![dx, dy].every(finite)) throw new Error('移动距离必须为有效数字');
  const value = structuredClone(item), shift = point => [clean(point[0] + dx), clean(point[1] + dy)];
  if (value.center) value.center = shift(value.center);
  else value.points = value.points.map(shift);
  return value;
}

export function itemBounds(items) {
  if (!items.length) return null;
  const points=items.flatMap(item=>item.center ? [[item.center[0]-(item.radius ?? 0),item.center[1]-(item.radius ?? 0)],
    [item.center[0]+(item.radius ?? 0),item.center[1]+(item.radius ?? 0)]] : item.points);
  const min=[0,1].map(axis=>Math.min(...points.map(point=>point[axis])));
  const max=[0,1].map(axis=>Math.max(...points.map(point=>point[axis])));
  return {min,max,center:min.map((value,axis)=>(value+max[axis])/2)};
}

// Rigid transforms also work on imported polygons and mixed selections. The source is never mutated.
export function transformItems(items, settings) {
  if (!items.length) throw new Error('请先选择要变换的对象');
  const {mode,dx,dy,angle,pivotX,pivotY,axisValue}=settings;
  if (!['move','rotate','mirror-x','mirror-y'].includes(mode)) throw new Error('请选择有效的变换方式');
  const required=mode==='move' ? [dx,dy] : mode==='rotate' ? [angle,pivotX,pivotY] : [axisValue];
  if (!required.every(finite)) throw new Error('请填写完整、有效的变换尺寸');
  if (mode==='move' && dx===0 && dy===0) throw new Error('移动距离不能同时为 0');
  if (mode==='rotate' && angle%360===0) throw new Error('旋转角度须产生实际转动');
  const c=Math.cos(radians(angle ?? 0)),s=Math.sin(radians(angle ?? 0));
  const point=([x,y])=>{
    if (mode==='move') return [clean(x+dx),clean(y+dy)];
    if (mode==='mirror-x') return [clean(2*axisValue-x),y];
    if (mode==='mirror-y') return [x,clean(2*axisValue-y)];
    return [clean(pivotX+(x-pivotX)*c-(y-pivotY)*s),clean(pivotY+(x-pivotX)*s+(y-pivotY)*c)];
  };
  return items.map(item=>{
    const result=structuredClone(item);
    if (result.center) result.center=point(result.center);
    else result.points=result.points.map(point);
    return result;
  });
}

export function editItemGeometry(item, key, value) {
  if (!finite(value)) throw new Error('位置和尺寸必须为有效数字');
  const result = structuredClone(item), [cx, cy] = itemCenter(item), rect = rectangleInfo(item.points);
  if (key === 'cx' || key === 'cy') return moveItem(item, key === 'cx' ? value - cx : 0, key === 'cy' ? value - cy : 0);
  if (key === 'radius' && item.center) {
    if (value <= 0) throw new Error('半径必须大于0');
    result.radius = value;
  } else if (rect && ['w', 'd', 'turn'].includes(key)) result.points = rectanglePoints({...rect, [key]:value});
  else throw new Error('这个外形不支持此尺寸修改');
  return result;
}

export function arrayCopies(item, count, spacing, direction) {
  if (!Number.isInteger(count) || count < 2 || count > 100) throw new Error('阵列总数须为2至100的整数（含原件）');
  if (![spacing, direction].every(finite) || spacing <= 0) throw new Error('中心间距必须大于0，方向须为有效角度');
  const angle = radians(direction);
  return Array.from({length:count - 1}, (_, i) => moveItem(item,
    spacing * (i + 1) * Math.cos(angle), spacing * (i + 1) * Math.sin(angle)));
}

export function snapGeometry(point, polygons, tolerance, excluded = null) {
  let best = null;
  const offer = (candidate, kind, priority) => {
    if (excluded && Math.hypot(candidate[0] - excluded[0], candidate[1] - excluded[1]) < 1e-9) return;
    const distance = Math.hypot(candidate[0] - point[0], candidate[1] - point[1]);
    if (distance <= tolerance && (!best || priority < best.priority || priority === best.priority && distance < best.distance))
      best = {point:candidate.map(clean), kind, priority, distance};
  };
  for (const points of polygons) {
    for (let i = 0; i < points.length; i++) {
      const a = points[i], b = points[(i + 1) % points.length], dx = b[0] - a[0], dy = b[1] - a[1], length2 = dx * dx + dy * dy;
      if (!length2) continue;
      offer(a, '端点', 0);
      offer([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], '中点', 1);
      const t = Math.max(0, Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length2));
      offer([a[0] + t * dx, a[1] + t * dy], '边线', 2);
    }
  }
  return best;
}
