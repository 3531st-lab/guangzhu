// A segmented perimeter cannot supply one automatic whole-roof height limit.
export function parapetInfo(roof) {
  if (roof?.parapet_segments != null) {
    const rows = roof.parapet_segments.filter(row => row.height_m > 0);
    const heights = rows.map(row => row.height_m);
    const low = Math.min(...heights), high = Math.max(...heights);
    return {segmented:true,cap:null,label:rows.length ?
      `${rows.length} 段 · ${low === high ? high : low + '–' + high} m` : '无女儿墙'};
  }
  const height = roof?.parapet_height_m;
  return {segmented:false,cap:Number.isFinite(height) ? height : null,
    label:Number.isFinite(height) ? `${height} m` : '未提供'};
}
