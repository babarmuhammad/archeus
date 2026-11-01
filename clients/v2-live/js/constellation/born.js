// What the map does for an object the chat has just made: the mark that carries the New tag, the link back that is drawn dashed, and the camera move that brings it into view.
// An entry is {id, kind, project}: the record, its kind (project, mission, idea) and the project it belongs to (its own id for a project). An idea has no mark of its own, so it stands for its project's hub.
export const BORN_MS = 6000;

// tags: mark ids that carry the tag. spokes: project ids whose spoke from the core is dashed. edges: mission ids whose relation to their project is dashed. focus: the first mark, the one the camera goes to.
export function planBorn(born, positions) {
  const plan = {tags: new Set(), spokes: new Set(), edges: new Set(), focus: null};
  for (const b of born || []) {
    const hub = positions.find(n => n.kind === 'Project' && n.id === b.project);
    const node = b.kind === 'mission' ? positions.find(n => n.id === b.id) : null;
    const target = node || hub;
    if (!target) continue;
    plan.tags.add(target.id);
    if (node) plan.edges.add(node.id); else plan.spokes.add(hub.id);
    plan.focus ??= target.id;
  }
  return plan;
}

// The camera goes to a mark only when it is off the scene (or under its edge bands), keeping its zoom; null when the mark is already in view.
export function cameraToward(n, camera, width, height, inset, margin = 28) {
  const x = n.x * camera.k + camera.x, y = n.y * camera.k + camera.y, top = inset.top + margin, bottom = height - inset.bottom - margin;
  if (x >= margin && x <= width - margin && y >= top && y <= bottom) return null;
  return {k: camera.k, x: width / 2 - n.x * camera.k, y: (top + bottom) / 2 - n.y * camera.k};
}
