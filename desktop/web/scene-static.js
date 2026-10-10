// Merge opaque, unlabelled static structure only; panels and semantic roof faces stay separate.
export function batchStatic(T, group) {
  const batches = new Map();
  for (const object of group.children) {
    const material = object.material;
    if ((!object.isMesh && !object.isLine) || object.isInstancedMesh || Object.keys(object.userData).length ||
      !material || Array.isArray(material) || material.transparent || material.map) continue;
    const key = [object.isLine, material.type, material.color.getHex(), material.side, material.opacity,
      material.roughness, material.metalness, object.castShadow, object.receiveShadow, object.renderOrder].join('/');
    if (!batches.has(key)) batches.set(key, []);
    batches.get(key).push(object);
  }
  for (const objects of batches.values()) {
    if (objects.length < 2) continue;
    const first = objects[0], coordinates = [], normals = [];
    for (const object of objects) {
      object.updateMatrix();
      const indexed = object.geometry.index;
      const transformed = indexed ? object.geometry.toNonIndexed() : object.geometry.clone();
      transformed.applyMatrix4(object.matrix);
      const position = transformed.getAttribute('position'), normal = transformed.getAttribute('normal');
      if (object.isLine) {
        const step = object.isLineSegments ? 2 : 1;
        for (let i = 0; i < position.count - 1; i += step) {
          for (const j of [i, i + 1]) coordinates.push(position.getX(j), position.getY(j), position.getZ(j));
        }
      } else {
        for (let i = 0; i < position.count; i++) {
          coordinates.push(position.getX(i), position.getY(i), position.getZ(i));
          normals.push(normal.getX(i), normal.getY(i), normal.getZ(i));
        }
      }
      transformed.dispose();
      object.geometry.dispose();
      if (object.material !== first.material) object.material.dispose();
      group.remove(object);
    }
    const geometry = new T.BufferGeometry();
    geometry.setAttribute('position', new T.Float32BufferAttribute(coordinates, 3));
    if (normals.length) geometry.setAttribute('normal', new T.Float32BufferAttribute(normals, 3));
    geometry.computeBoundingSphere();
    const merged = first.isLine ? new T.LineSegments(geometry, first.material) : new T.Mesh(geometry, first.material);
    merged.castShadow = first.castShadow;
    merged.receiveShadow = first.receiveShadow;
    merged.renderOrder = first.renderOrder;
    group.add(merged);
  }
}
