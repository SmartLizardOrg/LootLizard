export const MIN_ZOOM = 1;
export const MAX_ZOOM = 8;

const clamp = (value, lower, upper) => Math.min(upper, Math.max(lower, value));

/** A view is relative to the cropped map, so new capture sizes retain its focus. */
export function fitView() {
  return {zoom: MIN_ZOOM, centerX: 0.5, centerY: 0.5};
}

function normalizedView(state) {
  return {
    zoom: Number.isFinite(state?.zoom) ? clamp(state.zoom, MIN_ZOOM, MAX_ZOOM) : MIN_ZOOM,
    centerX: Number.isFinite(state?.centerX) ? clamp(state.centerX, 0, 1) : 0.5,
    centerY: Number.isFinite(state?.centerY) ? clamp(state.centerY, 0, 1) : 0.5,
  };
}

/** Dimensions and offsets are CSS pixels; map dimensions are cropped source pixels. */
export function viewTransform(state, metrics) {
  const {mapWidth, mapHeight, width, height} = metrics ?? {};
  if (![mapWidth, mapHeight, width, height].every(value =>
    Number.isFinite(value) && value > 0 && value <= Number.MAX_SAFE_INTEGER) ||
    mapWidth < 1 || mapHeight < 1) return null;

  const view = normalizedView(state);
  const scale = Math.min(width / mapWidth, height / mapHeight) * view.zoom;
  const drawWidth = mapWidth * scale;
  const drawHeight = mapHeight * scale;
  if (![scale, drawWidth, drawHeight].every(value => Number.isFinite(value) && value > 0)) return null;

  // A letterboxed axis stays centered. A larger axis stops at its map edges.
  const marginX = Math.min(0.5, width / (2 * drawWidth));
  const marginY = Math.min(0.5, height / (2 * drawHeight));
  const centerX = clamp(view.centerX, marginX, 1 - marginX);
  const centerY = clamp(view.centerY, marginY, 1 - marginY);
  return {
    zoom: view.zoom, centerX, centerY, scale, drawWidth, drawHeight,
    offsetX: width / 2 - centerX * drawWidth,
    offsetY: height / 2 - centerY * drawHeight,
  };
}

function stateFromTransform(transform) {
  return {zoom: transform.zoom, centerX: transform.centerX, centerY: transform.centerY};
}

/** Positive deltas follow the pointer: dragging right moves the map right. */
export function panView(state, dx, dy, metrics) {
  const transform = viewTransform(state, metrics);
  if (!transform) return normalizedView(state);
  const next = {
    zoom: transform.zoom,
    centerX: transform.centerX - (Number.isFinite(dx) ? clamp(dx, -transform.drawWidth, transform.drawWidth) / transform.drawWidth : 0),
    centerY: transform.centerY - (Number.isFinite(dy) ? clamp(dy, -transform.drawHeight, transform.drawHeight) / transform.drawHeight : 0),
  };
  return stateFromTransform(viewTransform(next, metrics));
}

/** Zoom around a CSS-pixel pointer, except where the map-edge clamp must intervene. */
export function zoomViewAt(state, factor, x, y, metrics) {
  const transform = viewTransform(state, metrics);
  if (!transform) return normalizedView(state);
  if (!Number.isFinite(factor) || factor <= 0) return stateFromTransform(transform);

  const pointerX = Number.isFinite(x) ? clamp(x, 0, metrics.width) : metrics.width / 2;
  const pointerY = Number.isFinite(y) ? clamp(y, 0, metrics.height) : metrics.height / 2;
  const zoom = clamp(transform.zoom * factor, MIN_ZOOM, MAX_ZOOM);
  const nextTransform = viewTransform({...transform, zoom}, metrics);
  const next = {
    zoom,
    centerX: (pointerX - transform.offsetX) / transform.drawWidth +
      (metrics.width / 2 - pointerX) / nextTransform.drawWidth,
    centerY: (pointerY - transform.offsetY) / transform.drawHeight +
      (metrics.height / 2 - pointerY) / nextTransform.drawHeight,
  };
  return stateFromTransform(viewTransform(next, metrics));
}
