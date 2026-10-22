/** Capture tickets prevent late worker replies from restoring stopped/old views. */
export class CaptureSession {
  constructor() { this.epoch = 0; this.sequence = 0; this.accepted = 0; this.active = false; this.source = null; this.result = null; this.updatedAt = 0; }
  begin(source) { this.stop(); this.source = source; this.active = true; return this.epoch; }
  invalidate() { this.epoch++; this.sequence = this.accepted = 0; this.result = null; this.updatedAt = 0; }
  stop() { this.invalidate(); this.active = false; this.source = null; }
  issue() { return this.active ? {epoch: this.epoch, sequence: ++this.sequence} : null; }
  accepts(ticket) { return this.active && ticket?.epoch === this.epoch && ticket.sequence === this.sequence && ticket.sequence > this.accepted; }
  accept(ticket, result, now = performance.now()) { if (!this.accepts(ticket)) return false; this.accepted = ticket.sequence; this.result = result; this.updatedAt = now; return true; }
  snapshot() { return {frameEpoch: this.epoch, sharing: this.active && this.source === 'screen', source: this.source, active: this.active}; }
}

export function project(matrix, x, y) {
  if (!Array.isArray(matrix) || matrix.length !== 3) return null;
  const w = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2];
  if (!Number.isFinite(w) || Math.abs(w) < 1e-12) return null;
  const result = [(matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / w,
                  (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / w];
  return result.every(Number.isFinite) ? result : null;
}

export function orderTargets(map, position, zone) {
  return map.points.map(point => ({...point,
    inside: zone ? Math.hypot(point.x-zone.centerX, point.y-zone.centerY) <= zone.radius+1e-12 : null,
    distance: position ? Math.hypot(point.x-position.x, point.y-position.y) * map.size_m : null,
  })).sort((a,b) => Number(b.inside === true)-Number(a.inside === true) ||
    (a.distance ?? Infinity)-(b.distance ?? Infinity) || a.id.localeCompare(b.id));
}
