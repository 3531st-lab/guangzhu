const radians = Math.PI / 180;
export const HEAT_COLORS = ['#1f3a66','#c87743','#d1493f'];
export function solarPosition(lat, lon, date, bjt) {
  const day = new Date(`${date}T00:00:00Z`), year = day.getUTCFullYear();
  const doy = (day - Date.UTC(year,0,0)) / 86400000;
  const g = 2 * Math.PI / 365 * (doy - 1 + (bjt - 20) / 24);
  const eq = 229.18 * (.000075 + .001868*Math.cos(g) - .032077*Math.sin(g) - .014615*Math.cos(2*g) - .040849*Math.sin(2*g));
  const dec = .006918 - .399912*Math.cos(g) + .070257*Math.sin(g) - .006758*Math.cos(2*g) + .000907*Math.sin(2*g) - .002697*Math.cos(3*g) + .00148*Math.sin(3*g);
  const ha = ((bjt*60 + eq + 4*lon - 480)/4 - 180)*radians, phi = lat*radians;
  const altitude = Math.asin(Math.max(-1,Math.min(1,Math.sin(phi)*Math.sin(dec)+Math.cos(phi)*Math.cos(dec)*Math.cos(ha))));
  const azimuth = Math.atan2(Math.sin(ha),Math.cos(ha)*Math.sin(phi)-Math.tan(dec)*Math.cos(phi))+Math.PI;
  return {altitude:altitude/radians,azimuth:azimuth/radians,direction:[Math.sin(azimuth)*Math.cos(altitude),Math.sin(altitude),-Math.cos(azimuth)*Math.cos(altitude)]};
}
export function heatColor(loss, threshold = 8) {
  if (!Number.isFinite(loss)) return '#998e83';
  const t = Math.max(0,Math.min(2,loss/Math.max(.001,threshold)*2)), i = Math.min(1,Math.floor(t));
  const colors = HEAT_COLORS.map(hex => hex.match(/[\da-f]{2}/g).map(v => parseInt(v,16)));
  return '#'+colors[i].map((v,j) => Math.round(v+(colors[i+1][j]-v)*(t-i)).toString(16).padStart(2,'0')).join('');
}
export function stringColor(id) {
  if (!id) return '#998e83';
  const hash = [...id].reduce((n,c) => (n*31+c.charCodeAt(0))>>>0,0);
  return `hsl(${(hash*137.508)%360},55%,48%)`;
}
export function normalizeScene(input) {
  const {project,design,parent_design,shading,electrical} = input;
  const roof = ['ground','carport'].includes(project.roof.type) ? design.installation_roof ?? project.roof : project.roof;
  const xs = roof.outline.map(p => p[0]), ys = roof.outline.map(p => p[1]);
  const center = [(Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2];
  const world = ([x,y,z=0]) => [x-center[0],roof.height_m+z,-(y-center[1])];
  const bearing = (roof.slope_azimuth_deg ?? 180) * radians;
  const station = ([x, y]) => -x * Math.sin(bearing) - y * Math.cos(bearing);
  const minimum = Math.min(...roof.outline.map(station));
  const elevation = p => roof.type === 'pitched' ? pitchedHeight(roof, p) :
    roof.type === 'metal' ? (station(p) - minimum) * Math.tan(roof.slope_deg * radians) : 0;
  const losses = new Map((shading?.version === design.version ? shading.modules : [])?.map(m => [m.id,m]) ?? []), strings = new Map();
  if (electrical?.version === design.version) for (const s of electrical.strings ?? []) for (const id of s.module_ids) strings.set(id,s);
  const wind = input.wind?.version === design.version ? input.wind : null;
  const windPanels = new Map((wind?.modules ?? []).map(m => [m.id, m]));
  const modules = design.modules.map(m => ({...m,position:world(m.center),points:m.corners.map(world),loss:losses.get(m.id)?.total_loss_pct ?? null,string:strings.get(m.id) ?? null}));
  const parent = parent_design?.version === design.parent_version ? parent_design : null;
  const ids = new Set(modules.map(m => m.id)), previous = new Set(parent?.modules.map(m => m.id));
  for (const m of modules) m.wind = windPanels.get(m.id) ?? null;
  return {...input,wind,roof,center,world,elevation,modules,span:Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys)),
    threshold:shading?.summary?.threshold_pct ?? 8,removed:(parent?.modules ?? []).filter(m => !ids.has(m.id)).map(m => ({...m,position:world(m.center),points:m.corners.map(world)})),
    added:new Set(parent ? modules.filter(m => !previous.has(m.id)).map(m => m.id) : []),electrical:electrical?.version === design.version ? electrical : null};
}
export function pitchedHeight(roof, point) {
  function distance(outline) {
    let inside = false, nearest = Infinity;
    outline.forEach((a, i) => {
      const b = outline[(i + 1) % outline.length], dx = b[0] - a[0], dy = b[1] - a[1];
      const t = Math.max(0, Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy)));
      nearest = Math.min(nearest, Math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy));
      if ((a[1] > point[1]) !== (b[1] > point[1]) && point[0] < dx * (point[1] - a[1]) / dy + a[0]) inside = !inside;
    });
    return inside ? 0 : nearest;
  }
  const plane = [...roof.planes].sort((a, b) => distance(a.outline) - distance(b.outline) || a.id - b.id)[0];
  const bearing = plane.slope_azimuth_deg * radians;
  const station = p => -p[0] * Math.sin(bearing) - p[1] * Math.cos(bearing);
  return plane.offset_m + (station(point) - Math.min(...plane.outline.map(station))) * Math.tan(plane.slope_deg * radians);
}
// Unit box X/Z span the exact module edges; Y is a display-only 4 cm thickness.
export function panelMatrix(module) {
  const [a,b,,d] = module.points, x = b.map((v,i) => v-a[i]), z = a.map((v,i) => v-d[i]);
  const n = [z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0]], scale = .04/Math.hypot(...n);
  return [...x,0,...n.map(v => v*scale),0,...z,0,...module.position,1];
}

// Cut a pile's displayed cap against the real inclined plane and the box's display-only 4 cm thickness.
export function pileContact(pile, members) {
  const distance = panel => Math.hypot(panel.center[0] - pile.point[0], panel.center[1] - pile.point[1]);
  const panel = [...members].sort((a, b) => distance(a) - distance(b))[0];
  const [a, b, , d] = panel.corners;
  const u = b.map((value, i) => value - a[i]), v = d.map((value, i) => value - a[i]);
  const determinant = u[0] * v[1] - u[1] * v[0];
  return {dx:(u[2] * v[1] - v[2] * u[1]) / determinant,
    dy:(v[2] * u[0] - u[2] * v[0]) / determinant, inset:.02 / Math.cos(panel.tilt * radians)};
}
