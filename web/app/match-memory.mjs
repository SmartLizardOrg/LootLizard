import {project} from './session.mjs';

const finiteMatrix = matrix => Array.isArray(matrix) && matrix.length === 3 &&
  matrix.every(row => Array.isArray(row) && row.length === 3 && row.every(Number.isFinite));

/** Reproject world coordinates; screen coordinates belong to one registration. */
function retainedPosition(position, matrix) {
  const screenCenter = finiteMatrix(matrix) && Number.isFinite(position.x) && Number.isFinite(position.y)
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

  /** Refresh community anchors without pretending that the retained map moved. */
  refreshPoints(map) {
    const current = this.#current;
    if (!current || map?.id !== current.result.registration.mapId || !Array.isArray(map.points)) return false;
    const {matrix, viewport = [0, 0, current.frame.width, current.frame.height]} = current.result.registration;
    const {width, height} = current.frame;
    const validViewport = Array.isArray(viewport) && viewport.length === 4 && viewport.every(Number.isFinite) &&
      viewport[0] < viewport[2] && viewport[1] < viewport[3];
    const canProject = finiteMatrix(matrix) && validViewport && Number.isFinite(width) && width > 0 &&
      Number.isFinite(height) && height > 0;
    const points = map.points.map(point => {
      const validWorld = Number.isFinite(point.x) && Number.isFinite(point.y) &&
        point.x >= 0 && point.x <= 1 && point.y >= 0 && point.y <= 1;
      const image = canProject && validWorld ? project(matrix, point.x, point.y) : null;
      const visible = Boolean(image && image[0] >= 0 && image[0] < width && image[1] >= 0 && image[1] < height &&
        image[0] >= viewport[0] && image[0] < viewport[2] && image[1] >= viewport[1] && image[1] < viewport[3]);
      return {id: point.id, visible, imageX: visible ? image[0] : null, imageY: visible ? image[1] : null};
    });
    this.#current = {...current, result: {...current.result, points}};
    return true;
  }

  reset() { this.#current = null; }
}
