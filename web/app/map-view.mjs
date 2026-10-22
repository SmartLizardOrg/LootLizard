import {project} from './session.mjs';

/** The main canvas contains only the registered map area inside the source. */
export function mapViewport(matrix, width, height) {
  if (![width, height].every(value => Number.isSafeInteger(value) && value > 0) ||
      !Array.isArray(matrix) || matrix.length !== 3 ||
      !matrix.every(row => Array.isArray(row) && row.length === 3 && row.every(Number.isFinite))) return null;
  const corners = [[0, 0], [1, 0], [1, 1], [0, 1]].map(([x, y]) => project(matrix, x, y));
  if (corners.some(point => !point)) return null;
  const left = Math.max(0, Math.floor(Math.min(...corners.map(point => point[0]))));
  const top = Math.max(0, Math.floor(Math.min(...corners.map(point => point[1]))));
  const right = Math.min(width, Math.ceil(Math.max(...corners.map(point => point[0]))));
  const bottom = Math.min(height, Math.ceil(Math.max(...corners.map(point => point[1]))));
  return right > left && bottom > top ? {x: left, y: top, width: right - left, height: bottom - top} : null;
}

/** A low-rate source thumbnail is bounded in both dimensions, without upscaling. */
export function sourcePreviewSize(width, height) {
  if (![width, height].every(value => Number.isSafeInteger(value) && value > 0)) return null;
  const scale = Math.min(1, 240 / width, 135 / height);
  return {width: Math.max(1, Math.floor(width * scale)), height: Math.max(1, Math.floor(height * scale))};
}
