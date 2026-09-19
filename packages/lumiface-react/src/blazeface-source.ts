import * as tf from "@tensorflow/tfjs-core";
import "@tensorflow/tfjs-backend-cpu";
import { setWasmPaths, version_wasm } from "@tensorflow/tfjs-backend-wasm";

import { BlazeFaceModel, type Detection } from "./blazeface.ts";
import type { FaceSignalSource, VideoRecorder } from "./controller.ts";
import { noFace, type Box, type FaceSignal, type StreamFormat } from "./types.ts";

export const MODEL_URL = "https://cdn.jsdelivr.net/gh/GA-MO/lumiface@main/packages/lumiface-react/models/face_detection_short/model.json";
export const WASM_URL = `https://cdn.jsdelivr.net/npm/@tensorflow/tfjs-backend-wasm@${version_wasm}/dist/`;

let backendInit: Promise<string> | null = null;

/** One backend for the page: tfjs cannot take two concurrent `setBackend` calls on an async backend
 *  (React StrictMode mounts a source twice), so every source shares the first initialisation. */
export function ensureBackend(backend: "wasm" | "cpu", wasmUrl: string): Promise<string> {
  backendInit ??= (async () => {
    if (backend === "wasm") {
      setWasmPaths(wasmUrl);
      try {
        if (await tf.setBackend("wasm")) {
          await tf.ready();
          return tf.getBackend();
        }
      } catch {}
    }
    await tf.setBackend("cpu");
    await tf.ready();
    return tf.getBackend();
  })();
  return backendInit;
}

export interface BlazeFaceSourceOptions {
  facing?: "user" | "environment";
  /** `model.json` of the BlazeFace short-range graph model; the default is the copy in this repository. */
  modelUrl?: string;
  /** Folder holding the tfjs-backend-wasm binaries; defaults to jsDelivr. */
  wasmUrl?: string;
  /** "wasm" (default) with the CPU backend as the fallback, or "cpu". */
  backend?: "wasm" | "cpu";
  detectIntervalMs?: number;
  width?: number;
  height?: number;
  /** MediaRecorder chunk length; the server decodes the stream, so shorter only means less latency at the end. */
  chunkMs?: number;
  /** Target bit rate of the recording. */
  videoBitsPerSecond?: number;
}

/** The recording format this browser can produce: VP8 in WebM (Chrome, Firefox, Edge) or H.264 in MP4 (Safari). */
export function recordingFormat(): { format: StreamFormat; mimeType: string } {
  if (typeof MediaRecorder === "undefined") throw new Error("MediaRecorder unavailable");
  for (const [mimeType, format] of [
    ["video/webm;codecs=vp8", "webm"],
    ["video/webm", "webm"],
    ["video/mp4;codecs=avc1", "mp4"],
    ["video/mp4", "mp4"],
  ] as const) {
    if (MediaRecorder.isTypeSupported(mimeType)) return { format, mimeType };
  }
  throw new Error("no supported recording format");
}

/** The largest face as the signal's box; BlazeFace reports no head angles. */
export function signalFromDetections(faces: Detection[], tsMs: number): FaceSignal {
  if (faces.length === 0) return noFace(tsMs);
  let best: Box | null = null;
  for (const f of faces) {
    if (!best || f.box.width * f.box.height > best.width * best.height) best = f.box;
  }
  return { tsMs, faceCount: faces.length, box: best, yaw: null, pitch: null };
}

/**
 * getUserMedia + TensorFlow.js BlazeFace (the short-range model, on the WASM backend) for the signals,
 * MediaRecorder for the stream the server judges. Owns a `<video>` element you mount yourself (mirror it
 * with CSS for a front camera; signals and the recording stay un-mirrored).
 */
export class BlazeFaceSource implements FaceSignalSource, VideoRecorder {
  readonly video: HTMLVideoElement;
  readonly format: StreamFormat;
  private readonly mimeType: string;
  private readonly options: Required<BlazeFaceSourceOptions>;
  private readonly listeners = new Set<(s: FaceSignal) => void>();
  private stream: MediaStream | null = null;
  private detector: BlazeFaceModel | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private recorder: MediaRecorder | null = null;
  private detecting = false;
  private warned = false;
  private readonly startedAt = performance.now();

  constructor(options: BlazeFaceSourceOptions = {}) {
    this.options = {
      facing: "user",
      modelUrl: MODEL_URL,
      wasmUrl: WASM_URL,
      backend: "wasm",
      detectIntervalMs: 66,
      width: 1280,
      height: 720,
      chunkMs: 250,
      videoBitsPerSecond: 1_500_000,
      ...options,
    };
    const rec = recordingFormat();
    this.format = rec.format;
    this.mimeType = rec.mimeType;
    this.video = document.createElement("video");
    this.video.autoplay = true;
    this.video.muted = true;
    this.video.playsInline = true;
  }

  get isMirrored() {
    return this.options.facing === "user";
  }

  get aspectRatio() {
    return this.video.videoHeight === 0 ? 1 : this.video.videoWidth / this.video.videoHeight;
  }

  async initialize() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: this.options.facing, width: { ideal: this.options.width }, height: { ideal: this.options.height } },
    });
    this.video.srcObject = this.stream;
    await this.video.play();
    await ensureBackend(this.options.backend, this.options.wasmUrl);
    this.detector = await BlazeFaceModel.load(this.options.modelUrl);
  }

  get backend() {
    return tf.getBackend();
  }

  subscribe(listener: (s: FaceSignal) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  startStream() {
    this.timer ??= setInterval(() => void this.tick(), this.options.detectIntervalMs);
  }

  stopStream() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  private async tick() {
    if (this.detecting || !this.detector) return;
    this.detecting = true;
    const ts = Math.round(performance.now() - this.startedAt);
    let signal: FaceSignal;
    try {
      signal =
        this.video.readyState < 2
          ? noFace(ts)
          : signalFromDetections(await this.detector.detect(this.video), ts);
    } catch (e) {
      if (!this.warned) {
        this.warned = true;
        console.warn("lumiface: face detection failed, reporting no face", e);
      }
      signal = noFace(ts);
    } finally {
      this.detecting = false;
    }
    for (const l of this.listeners) l(signal);
  }

  private now() {
    return Math.round(performance.now() - this.startedAt);
  }

  /** Records the camera stream; each chunk goes out stamped with the signal-clock time of its first frame. */
  start(onChunk: (data: Blob, tsMs: number) => void) {
    if (this.recorder || !this.stream) return;
    const recorder = new MediaRecorder(this.stream, { mimeType: this.mimeType, videoBitsPerSecond: this.options.videoBitsPerSecond });
    let chunkStart = this.now();
    recorder.ondataavailable = (e) => {
      const ts = chunkStart;
      chunkStart = this.now();
      if (e.data.size > 0) onChunk(e.data, ts);
    };
    recorder.onstart = () => {
      chunkStart = this.now();
    };
    this.recorder = recorder;
    recorder.start(this.options.chunkMs);
  }

  stop() {
    const r = this.recorder;
    this.recorder = null;
    if (r && r.state !== "inactive") r.stop();
  }


  dispose() {
    this.stopStream();
    this.stop();
    this.listeners.clear();
    this.detector?.dispose();
    this.detector = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.video.srcObject = null;
  }
}
