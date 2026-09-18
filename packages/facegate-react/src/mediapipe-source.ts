import { FaceLandmarker, FilesetResolver, type FaceLandmarkerResult } from "@mediapipe/tasks-vision";

import type { FaceSignalSource, FrameCapturer } from "./controller.ts";
import { noFace, type FaceSignal, type Point } from "./types.ts";

const TASKS_VISION_URL = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const NOSE_TIP = 1;
const RIGHT_EYE = [33, 133, 159, 145];
const LEFT_EYE = [362, 263, 386, 374];

export interface MediaPipeSourceOptions {
  facing?: "user" | "environment";
  /** Folder holding the tasks-vision wasm files; defaults to jsDelivr. */
  wasmUrl?: string;
  modelUrl?: string;
  delegate?: "GPU" | "CPU";
  /** Flip to -1 if a turn to the user's left reports negative yaw on your setup. */
  yawSign?: 1 | -1;
  detectIntervalMs?: number;
  jpegQuality?: number;
  width?: number;
  height?: number;
}

function centre(landmarks: { x: number; y: number }[], indices: number[]): Point {
  let x = 0;
  let y = 0;
  for (const i of indices) {
    x += landmarks[i].x;
    y += landmarks[i].y;
  }
  return { x: x / indices.length, y: y / indices.length };
}

function blendshape(result: FaceLandmarkerResult, i: number, name: string): number | null {
  const hit = result.faceBlendshapes?.[i]?.categories.find((c) => c.categoryName === name);
  return hit ? hit.score : null;
}

function angles(result: FaceLandmarkerResult, i: number): [number | null, number | null] {
  const m = result.facialTransformationMatrixes?.[i]?.data;
  if (!m) return [null, null];
  const deg = 180 / Math.PI;
  return [Math.atan2(m[8], m[10]) * deg, Math.atan2(-m[9], m[10]) * deg];
}

export function signalFromResult(result: FaceLandmarkerResult, tsMs: number, yawSign: 1 | -1): FaceSignal {
  const faces = result.faceLandmarks;
  if (!faces || faces.length === 0) return noFace(tsMs);
  let best = 0;
  let bestArea = -1;
  const boxes = faces.map((landmarks) => {
    let minX = 1, minY = 1, maxX = 0, maxY = 0;
    for (const p of landmarks) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    return { left: minX, top: minY, width: maxX - minX, height: maxY - minY };
  });
  boxes.forEach((b, i) => {
    const area = b.width * b.height;
    if (area > bestArea) {
      bestArea = area;
      best = i;
    }
  });
  const landmarks = faces[best];
  const blinkLeft = blendshape(result, best, "eyeBlinkLeft");
  const blinkRight = blendshape(result, best, "eyeBlinkRight");
  const smileLeft = blendshape(result, best, "mouthSmileLeft");
  const smileRight = blendshape(result, best, "mouthSmileRight");
  const [yaw, pitch] = angles(result, best);
  return {
    tsMs,
    faceCount: faces.length,
    box: boxes[best],
    eyeOpenLeft: blinkLeft === null ? null : 1 - blinkLeft,
    eyeOpenRight: blinkRight === null ? null : 1 - blinkRight,
    smile: smileLeft === null || smileRight === null ? null : (smileLeft + smileRight) / 2,
    yaw: yaw === null ? null : yaw * yawSign,
    pitch,
    nose: { x: landmarks[NOSE_TIP].x, y: landmarks[NOSE_TIP].y },
    leftEye: centre(landmarks, LEFT_EYE),
    rightEye: centre(landmarks, RIGHT_EYE),
  };
}

/**
 * getUserMedia + MediaPipe FaceLandmarker. Owns a `<video>` element you mount
 * yourself (mirror it with CSS for a front camera; signals stay un-mirrored).
 */
export class MediaPipeSource implements FaceSignalSource, FrameCapturer {
  readonly video: HTMLVideoElement;
  private readonly options: Required<MediaPipeSourceOptions>;
  private readonly listeners = new Set<(s: FaceSignal) => void>();
  private stream: MediaStream | null = null;
  private landmarker: FaceLandmarker | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private detecting = false;
  private readonly startedAt = performance.now();

  constructor(options: MediaPipeSourceOptions = {}) {
    this.options = {
      facing: "user",
      wasmUrl: TASKS_VISION_URL,
      modelUrl: MODEL_URL,
      delegate: "GPU",
      yawSign: 1,
      detectIntervalMs: 66,
      jpegQuality: 0.9,
      width: 1280,
      height: 720,
      ...options,
    };
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
    const vision = await FilesetResolver.forVisionTasks(this.options.wasmUrl);
    this.landmarker = await FaceLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath: this.options.modelUrl, delegate: this.options.delegate },
      runningMode: "VIDEO",
      numFaces: 2,
      outputFaceBlendshapes: true,
      outputFacialTransformationMatrixes: true,
    });
  }

  subscribe(listener: (s: FaceSignal) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  startStream() {
    this.timer ??= setInterval(() => this.tick(), this.options.detectIntervalMs);
  }

  stopStream() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  private tick() {
    if (this.detecting || !this.landmarker) return;
    this.detecting = true;
    const ts = Math.round(performance.now() - this.startedAt);
    let signal: FaceSignal;
    try {
      signal =
        this.video.readyState < 2
          ? noFace(ts)
          : signalFromResult(this.landmarker.detectForVideo(this.video, ts), ts, this.options.yawSign);
    } catch {
      signal = noFace(ts);
    } finally {
      this.detecting = false;
    }
    for (const l of this.listeners) l(signal);
  }

  captureJpeg(): Promise<Blob> {
    const canvas = document.createElement("canvas");
    canvas.width = this.video.videoWidth;
    canvas.height = this.video.videoHeight;
    canvas.getContext("2d")!.drawImage(this.video, 0, 0);
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("toBlob failed"))), "image/jpeg", this.options.jpegQuality);
    });
  }

  dispose() {
    this.stopStream();
    this.listeners.clear();
    this.landmarker?.close();
    this.landmarker = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.video.srcObject = null;
  }
}
