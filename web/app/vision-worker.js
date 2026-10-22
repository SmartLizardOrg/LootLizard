/* Client-only CV worker. No screenshots/references are uploaded. */
const PYODIDE_VERSION = "314.0.7";
const PYODIDE_INDEX = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const SOURCE_ROOT = new URL("../cv/", import.meta.url);
const MODULES = ["__init__", "core", "registration", "marker_pipeline", "self_marker", "vision", "zone_vision"];
let runtimePromise = null;
let runtime = null;
let engine = null;
let busy = false;
let generation = 0;

function progress(message) { self.postMessage({type: "progress", message: String(message)}); }
function reason(error) { return String(error?.message || error).slice(0, 1600); }

async function sourceText(url) {
  const response = await fetch(url, {credentials: "same-origin"});
  if (!response.ok) throw new Error(`Could not load CV source (${response.status}): ${url.pathname}`);
  const text = await response.text();
  if (text.length > 150000) throw new Error("CV source exceeds its proof-of-concept limit.");
  return text;
}

async function loadRuntime() {
  if (!runtimePromise) runtimePromise = (async () => {
    progress("Loading the browser Python runtime…");
    const {loadPyodide} = await import(`${PYODIDE_INDEX}pyodide.mjs`);
    const py = await loadPyodide({indexURL: PYODIDE_INDEX});
    progress("Loading NumPy, Pillow and OpenCV locally…");
    await py.loadPackage(["numpy", "pillow", "opencv-python"], {messageCallback: progress});
    const texts = await Promise.all(MODULES.map(name => sourceText(new URL(`${name}.py`, SOURCE_ROOT))));
    py.FS.mkdirTree("/home/pyodide/lootlizard");
    texts.forEach((text, i) => py.FS.writeFile(`/home/pyodide/lootlizard/${MODULES[i]}.py`, text));
    py.FS.writeFile("/home/pyodide/python_bridge.py", await sourceText(new URL("python_bridge.py", import.meta.url)));
    await py.runPythonAsync("from python_bridge import BrowserVisionEngine, capabilities\n_browser_capabilities = capabilities()");
    runtime = py;
    return py;
  })().catch(error => { runtimePromise = null; throw error; });
  return runtimePromise;
}

function plain(proxy) {
  if (proxy && typeof proxy.toJs === "function") {
    // Pyodide 314 maps Python None to undefined. The RPC contract deliberately
    // uses explicit nulls so unknown geometry survives JSON/logging unchanged.
    try { return normalizeNulls(proxy.toJs({dict_converter: Object.fromEntries, create_pyproxies: false})); }
    finally { proxy.destroy(); }
  }
  return normalizeNulls(proxy);
}

function normalizeNulls(value) {
  if (value === undefined) return null;
  if (Array.isArray(value)) return value.map(normalizeNulls);
  if (value && typeof value === "object")
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, normalizeNulls(child)]));
  return value;
}

function byteView(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength > 2400 * 2400 * 4)
    throw new Error("An image requires a bounded transferred RGBA ArrayBuffer.");
  return new Uint8Array(buffer);
}

self.onmessage = async ({data: message}) => {
  const {id, type, ticket} = message || {};
  if (type === "clear") {
    generation++;
    const cleared = engine ? plain(engine.clear()) : {count: 0};
    self.postMessage({id, type: "cleared", ...cleared});
    return;
  }
  if (!["init", "references", "analyze"].includes(type)) {
    self.postMessage({id, type: "error", ticket, reason: "Unknown worker request."});
    return;
  }
  if (busy) {
    self.postMessage({id, type: "error", ticket, reason: "The CV worker is already processing a request."});
    return;
  }
  busy = true;
  const requestGeneration = generation;
  let converted = null;
  try {
    const py = await loadRuntime();
    if (requestGeneration !== generation) throw new Error("Request cancelled by worker clear.");
    if (type === "init") {
      if (!Array.isArray(message.maps)) throw new Error("An initial map-data array is required.");
      const constructor = py.globals.get("BrowserVisionEngine");
      let replacement;
      try { replacement = constructor(JSON.stringify(message.maps)); }
      finally { constructor.destroy(); }
      if (engine) engine.destroy();
      engine = replacement;
      const capabilityProxy = py.globals.get("_browser_capabilities");
      self.postMessage({id, type: "ready", version: PYODIDE_VERSION, capabilities: plain(capabilityProxy)});
    } else {
      if (!engine) throw new Error("Initialize the worker before loading references or analyzing.");
      if (type === "references") {
        if (!Array.isArray(message.references) || message.references.length > 8)
          throw new Error("Provide at most eight complete map references.");
        const records = message.references.map(record => ({mapId: record.mapId,
          rgba: byteView(record.rgba), width: record.width, height: record.height}));
        converted = py.toPy(records);
        const loaded = plain(engine.set_references(converted));
        generation++;
        self.postMessage({id, type: "references", ...loaded});
      } else {
        converted = py.toPy(byteView(message.rgba));
        // A synchronous Python call keeps one CPU-bound analysis at a time.
        // The controller must also discard tickets from replaced/ended captures.
        // Tickets are controller transport data, not CV inputs. Keep their
        // exact structured-cloned value in JavaScript rather than turning an
        // {epoch,sequence} object into a Python JsProxy and back again.
        const result = plain(engine.analyze_rgba(converted, message.width, message.height,
          message.context || "live"));
        if (requestGeneration !== generation) throw new Error("Stale analysis was discarded.");
        self.postMessage({id, type: "result", ...result, ticket: ticket ?? null});
      }
    }
  } catch (error) {
    self.postMessage({id, type: "error", ticket, reason: reason(error)});
  } finally {
    if (converted && typeof converted.destroy === "function") converted.destroy();
    busy = false;
  }
};
