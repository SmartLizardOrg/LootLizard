/** Small, fixed-size location symbols shared by the map, list and legend. */
export const LOCATION_KINDS = Object.freeze(['secret_room', 'security_room', 'bear_cave', 'tunnel_entrance', 'supply_cache']);
const SYMBOLS = Object.freeze({
  secret_room: {label: 'Secret room', color: '#ffd184', path: 'M5 20V4h13v16M3 20h18M9 20V8h6v12M12.5 13h.1'},
  security_room: {label: 'Security room', color: '#86d9ed', path: 'M7 10V7a5 5 0 0 1 10 0v3M5 10h14v11H5ZM12 14v3'},
  bear_cave: {label: 'Bear cave entrance', color: '#efb5d7', path: 'M2 21 5 9l5-6 5 3 4 7 3 8ZM8 21v-6a4 4 0 0 1 8 0v6M6 8l3 3m6-5-2 4'},
  tunnel_entrance: {label: 'Tunnel entrance', color: '#b1df94', path: 'M3 21V11a9 9 0 0 1 18 0v10M7 21V11a5 5 0 0 1 10 0v10M1 21h22M4 7l4 2m12-2-4 2M12 2v4'},
  supply_cache: {label: 'Pillar supply cache', color: '#d2b8ff', path: 'M3 9h18v12H3ZM3 13h18M7 9v12m10-12v12M9 9V6a3 3 0 0 1 6 0v3M10 14h4v4h-4Z'},
});
export function locationKind(point) {
  return LOCATION_KINDS.includes(point?.kind) ? point.kind : 'secret_room';
}
export function locationLabel(kind) { return SYMBOLS[LOCATION_KINDS.includes(kind) ? kind : 'secret_room'].label; }
export function locationIconSVG(kind) {
  const symbol = SYMBOLS[LOCATION_KINDS.includes(kind) ? kind : 'secret_room'];
  return `<svg viewBox="0 0 24 24" fill="none" stroke="${symbol.color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${symbol.path}"/></svg>`;
}
export function presentLocationKinds(points) {
  const present = new Set(points.map(locationKind));
  return LOCATION_KINDS.filter(kind => present.has(kind));
}
const intersects = (a, b, gap = 3) => a.x < b.x + b.width + gap && a.x + a.width + gap > b.x && a.y < b.y + b.height + gap && a.y + a.height + gap > b.y;
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const directions = [[1,-1],[-1,-1],[1,1],[-1,1],[0,-1],[0,1],[1,0],[-1,0]];
/** Coordinates and dimensions are CSS pixels. Only badges move; anchors never do. */
export function layoutLocationMarkers(points, width, height) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return [];
  const visible = points.filter(point => Number.isFinite(point.x) && Number.isFinite(point.y) && point.x >= 0 && point.x <= width && point.y >= 0 && point.y <= height);
  const occupied = [], anchorBoxes = visible.map(point => ({x: point.x - 4, y: point.y - 4, width: 8, height: 8}));
  return visible.map(point => {
    const anchor = {x: point.x, y: point.y};
    let badge = null, leader = null;
    // Prefer a numbered icon. An icon-only badge is useful in crowded towns.
    search: for (const numbered of [true, false]) {
      const badgeWidth = numbered ? (String(point.index).length > 2 ? 47 : 40) : 22, badgeHeight = 24;
      for (const distance of [9, 21, 33]) for (const [dx, dy] of directions) {
        const candidate = {x: dx > 0 ? anchor.x + distance : dx < 0 ? anchor.x - distance - badgeWidth : anchor.x - badgeWidth / 2,
          y: dy > 0 ? anchor.y + distance : dy < 0 ? anchor.y - distance - badgeHeight : anchor.y - badgeHeight / 2,
          width: badgeWidth, height: badgeHeight, numbered};
        if (candidate.x < 1 || candidate.y < 1 || candidate.x + badgeWidth > width - 1 || candidate.y + badgeHeight > height - 1) continue;
        if (occupied.some(box => intersects(candidate, box)) || anchorBoxes.some(box => intersects(candidate, box, 1))) continue;
        const end = {x: clamp(anchor.x, candidate.x, candidate.x + badgeWidth), y: clamp(anchor.y, candidate.y, candidate.y + badgeHeight)};
        if (Math.hypot(end.x - anchor.x, end.y - anchor.y) > 48) continue;
        badge = candidate; leader = end; occupied.push(candidate); break search;
      }
    }
    return {...point, kind: locationKind(point), anchor, badge, leader};
  });
}
const paths = new Map();
function iconPath(kind) {
  if (!paths.has(kind)) paths.set(kind, new Path2D(SYMBOLS[kind].path));
  return paths.get(kind);
}
/** Call with a canvas context scaled so one unit is one displayed CSS pixel. */
export function drawLocationMarkers(ctx, markers) {
  for (const marker of markers) {
    if (!marker.badge) continue;
    const symbol = SYMBOLS[marker.kind], box = marker.badge;
    ctx.save();ctx.lineCap = 'round';ctx.lineJoin = 'round';
    ctx.beginPath();ctx.moveTo(marker.anchor.x, marker.anchor.y);ctx.lineTo(marker.leader.x, marker.leader.y);
    ctx.strokeStyle = '#0b1118';ctx.lineWidth = 3;ctx.stroke();ctx.strokeStyle = symbol.color;ctx.lineWidth = 1;ctx.stroke();
    ctx.fillStyle = '#101923';ctx.fillRect(box.x, box.y, box.width, box.height);
    ctx.strokeStyle = '#0b1118';ctx.lineWidth = 3;ctx.strokeRect(box.x, box.y, box.width, box.height);
    ctx.strokeStyle = symbol.color;ctx.lineWidth = 1;ctx.strokeRect(box.x, box.y, box.width, box.height);
    ctx.save();ctx.translate(box.x + 3, box.y + 4);ctx.scale(16 / 24, 16 / 24);ctx.lineWidth = 1.8;ctx.stroke(iconPath(marker.kind));ctx.restore();
    if (box.numbered) {ctx.fillStyle = symbol.color;ctx.font = 'bold 11px sans-serif';ctx.textAlign = 'center';ctx.textBaseline = 'middle';ctx.fillText(String(marker.index), box.x + (box.width + 17) / 2, box.y + box.height / 2 + .5);}
    ctx.restore();
  }
  // Draw true locations last, so an offset badge/leader cannot hide an anchor.
  for (const marker of markers) {
    const {x,y} = marker.anchor;
    ctx.save();ctx.strokeStyle = '#080e14';ctx.fillStyle = SYMBOLS[marker.kind].color;ctx.lineWidth = 2;
    ctx.beginPath();ctx.arc(x,y,2.2,0,Math.PI*2);ctx.fill();ctx.stroke();
    ctx.beginPath();ctx.moveTo(x-5,y);ctx.lineTo(x-3.8,y);ctx.moveTo(x+3.8,y);ctx.lineTo(x+5,y);ctx.moveTo(x,y-5);ctx.lineTo(x,y-3.8);ctx.moveTo(x,y+3.8);ctx.lineTo(x,y+5);
    ctx.strokeStyle = SYMBOLS[marker.kind].color;ctx.lineWidth = 1;ctx.stroke();ctx.restore();
  }
}
