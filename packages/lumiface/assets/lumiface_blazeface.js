const TFJS = "https://cdn.jsdelivr.net/npm/@tensorflow";
const TFJS_VERSION = "4.22.0";

const INPUT = 128;
const STRIDES = [8, 16, 16, 16];
const SCORE_THRESHOLD = 0.5;
const NMS_IOU = 0.3;
const VALUES_PER_ANCHOR = 17;

let anchors = null;

function shortRangeAnchors() {
  if (anchors) return anchors;
  anchors = [];
  let layer = 0;
  while (layer < STRIDES.length) {
    const stride = STRIDES[layer];
    let perCell = 0;
    let last = layer;
    while (last < STRIDES.length && STRIDES[last] === stride) {
      perCell += 2;
      last++;
    }
    const cells = Math.ceil(INPUT / stride);
    for (let y = 0; y < cells; y++) {
      for (let x = 0; x < cells; x++) {
        for (let a = 0; a < perCell; a++) anchors.push([(x + 0.5) / cells, (y + 0.5) / cells]);
      }
    }
    layer = last;
  }
  return anchors;
}

function iou(a, b) {
  const x1 = Math.max(a[0], b[0]);
  const y1 = Math.max(a[1], b[1]);
  const x2 = Math.min(a[0] + a[2], b[0] + b[2]);
  const y2 = Math.min(a[1] + a[3], b[1] + b[3]);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const union = a[2] * a[3] + b[2] * b[3] - inter;
  return union <= 0 ? 0 : inter / union;
}

function decode(raw, padX, padY) {
  const found = [];
  const sx = 1 - 2 * padX;
  const sy = 1 - 2 * padY;
  shortRangeAnchors().forEach(([ax, ay], i) => {
    const o = i * VALUES_PER_ANCHOR;
    const score = 1 / (1 + Math.exp(-Math.min(100, Math.max(-100, raw[o]))));
    if (score < SCORE_THRESHOLD) return;
    const cx = raw[o + 1] / INPUT + ax;
    const cy = raw[o + 2] / INPUT + ay;
    const w = raw[o + 3] / INPUT;
    const h = raw[o + 4] / INPUT;
    found.push({ score, box: [(cx - w / 2 - padX) / sx, (cy - h / 2 - padY) / sy, w / sx, h / sy] });
  });
  found.sort((a, b) => b.score - a.score);
  const kept = [];
  for (const d of found) if (kept.every((k) => iou(k.box, d.box) < NMS_IOU)) kept.push(d);
  return kept;
}

let runtime = null;

/** tfjs and its backend once per page: a second concurrent setBackend on the async WASM backend corrupts the engine. */
function loadRuntime(options) {
  runtime ??= (async () => {
    const base = options.tfjsUrl ?? `${TFJS}/`;
    const v = options.tfjsVersion ?? TFJS_VERSION;
    const tf = await import(`${base}tfjs-core@${v}/+esm`);
    await import(`${base}tfjs-backend-cpu@${v}/+esm`);
    const wasm = await import(`${base}tfjs-backend-wasm@${v}/+esm`);
    const converter = await import(`${base}tfjs-converter@${v}/+esm`);
    wasm.setWasmPaths(options.wasmUrl ?? `${base}tfjs-backend-wasm@${v}/dist/`);
    let ready = false;
    if ((options.backend ?? "wasm") === "wasm") {
      try {
        ready = await tf.setBackend("wasm");
      } catch (_) {}
    }
    if (!ready) await tf.setBackend("cpu");
    await tf.ready();
    return { tf, converter };
  })();
  return runtime;
}

async function create(options = {}) {
  const { tf, converter } = await loadRuntime(options);
  const model = await converter.loadGraphModel(options.modelUrl);
  const canvas = document.createElement("canvas");
  canvas.width = INPUT;
  canvas.height = INPUT;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  return {
    backend: tf.getBackend(),
    async detect(video) {
      const w = video.videoWidth;
      const h = video.videoHeight;
      if (video.readyState < 2 || w === 0 || h === 0) return JSON.stringify({ faces: [] });
      const padX = w >= h ? 0 : (1 - w / h) / 2;
      const padY = w >= h ? (1 - h / w) / 2 : 0;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, INPUT, INPUT);
      ctx.drawImage(video, padX * INPUT, padY * INPUT, (1 - 2 * padX) * INPUT, (1 - 2 * padY) * INPUT);
      const output = tf.tidy(() => model.execute(tf.expandDims(tf.sub(tf.div(tf.cast(tf.browser.fromPixels(canvas), "float32"), 127.5), 1), 0)));
      try {
        const faces = decode(await output.data(), padX, padY).map((d) => ({ box: d.box, score: d.score }));
        return JSON.stringify({ faces });
      } finally {
        output.dispose();
      }
    },
    close() {
      model.dispose();
    },
  };
}

const RECORDING_TYPES = [
  ["video/webm;codecs=vp8", "webm"],
  ["video/webm", "webm"],
  ["video/mp4;codecs=avc1", "mp4"],
  ["video/mp4", "mp4"],
];

function recordingFormat() {
  if (typeof MediaRecorder === "undefined") return null;
  for (const [mimeType, format] of RECORDING_TYPES) if (MediaRecorder.isTypeSupported(mimeType)) return { mimeType, format };
  return null;
}

let recorder = null;

/** Records the video element's stream; `onChunk(arrayBuffer, startMs)` gets each chunk with the clock value the
 *  caller's `now()` returned when the chunk began. */
function startRecording(video, chunkMs, bitsPerSecond, now, onChunk) {
  const rec = recordingFormat();
  if (!rec || recorder) return rec ? rec.format : null;
  const stream = video.srcObject;
  recorder = new MediaRecorder(stream, { mimeType: rec.mimeType, videoBitsPerSecond: bitsPerSecond });
  let chunkStart = now();
  recorder.onstart = () => {
    chunkStart = now();
  };
  recorder.ondataavailable = (e) => {
    const ts = chunkStart;
    chunkStart = now();
    if (e.data.size > 0) e.data.arrayBuffer().then((buf) => onChunk(buf, ts));
  };
  recorder.start(chunkMs);
  return rec.format;
}

function stopRecording() {
  const r = recorder;
  recorder = null;
  if (r && r.state !== "inactive") r.stop();
}

window.lumifaceBlazeFace = { create, recordingFormat, startRecording, stopRecording };
