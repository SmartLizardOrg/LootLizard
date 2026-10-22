import {project} from './session.mjs';

/** Reproject world coordinates; screen coordinates belong to one registration. */
function retainedPosition(position, matrix) {
  const validMatrix = Array.isArray(matrix) && matrix.length === 3 &&
    matrix.every(row => Array.isArray(row) && row.length === 3 && row.every(Number.isFinite));
  const screenCenter = validMatrix && Number.isFinite(position.x) && Number.isFinite(position.y)
    ? project(matrix, position.x, position.y)
    : null;
  return {...position, screenCenter};
}

/**
 * Hold the last registered map and its exact source frame for one match.
 *
 * Unregistered frames leave the snapshot untouched. A fresh registration keeps
 * only world-coordinate position/circle data from the same map when those
 * detections are absent. Their independent timestamps expose that older age.
 * The frame is retained by reference; its pixels are never copied here.
 */
export class MatchMapMemory {
  #current = null;

  /** The current paired snapshot, or null before recognition/after reset. */
  get current() { return this.#current; }

  snapshot() { return this.#current; }

  /** Return true only when a registered result and frame replace the snapshot. */
  update(result, frame, now) {
    const mapId = result?.registration?.mapId;
    if (typeof mapId !== 'string' || !mapId || frame == null ||
        !Number.isFinite(now) || now < 0) return false;

    const previous = this.#current?.result.registration.mapId === mapId ? this.#current : null;
    const freshPosition = result.position ?? null;
    const freshZone = result.zone ?? null;
    const position = freshPosition ?? (previous?.result.position
      ? retainedPosition(previous.result.position, result.registration.matrix)
      : null);
    // Safe-zone center and radius are already normalized world coordinates.
    const zone = freshZone ?? previous?.result.zone ?? null;

    this.#current = {
      result: {...result, position, zone},
      frame,
      mapUpdatedAt: now,
      positionUpdatedAt: freshPosition ? now : previous?.positionUpdatedAt ?? null,
      zoneUpdatedAt: freshZone ? now : previous?.zoneUpdatedAt ?? null,
    };
    return true;
  }

  reset() { this.#current = null; }
}
