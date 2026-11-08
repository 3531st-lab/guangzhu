// View selection is intentionally separate from saved geometry and the undo history.
export function normalizeSelection(selection, items, parts=[]) {
  if (!selection) return null;
  if (selection.kind==='part') return parts.some(part=>part.id===selection.active) ? {kind:'part',ids:[selection.active],active:selection.active} : null;
  if (selection.kind!=='item') return null;
  const available=new Set(items.map(item=>item.id));
  const ids=[...new Set(selection.ids ?? [])].filter(id=>available.has(id));
  return ids.length ? {kind:'item',ids,active:ids.includes(selection.active) ? selection.active : ids.at(-1)} : null;
}

export function selectObject(selection, {kind,id}, extend=false) {
  if (!['item','part'].includes(kind) || id == null) return null;
  if (!extend || kind!=='item' || selection?.kind!=='item') return {kind,ids:[id],active:id};
  const ids=selection.ids.includes(id) ? selection.ids.filter(value=>value!==id) : [...selection.ids,id];
  return ids.length ? {kind,ids,active:ids.includes(id) ? id : ids.at(-1)} : null;
}

export const selectionRefs=selection=>(selection?.ids ?? []).map(id=>({kind:selection.kind,id}));
export const selectedItems=(selection,items)=>selection?.kind==='item' ? items.filter(item=>selection.ids.includes(item.id)) : [];
