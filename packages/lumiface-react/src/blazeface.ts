import { loadGraphModel, type GraphModel } from "@tensorflow/tfjs-converter";
import * as tf from "@tensorflow/tfjs-core";

import type { Box } from "./types.ts";

/**
 * BlazeFace short-range (MediaPipe `face_detection_short_range`)
 * on the web and Android: a 128x128 input, 896 anchors, one score and a box (plus six keypoints,
 * unused here) per anchor. Decoding follows MediaPipe's SsdAnchorsCalculator and
 * TensorsToDetectionsCalculator options for that model.
 */
export const INPUT_SIZE = 128;
const STRIDES = [8, 16, 16, 16];
const MIN_SCALE = 0.1484375;
const MAX_SCALE = 0.75;
const SCORE_THRESHOLD = 0.5;
const NMS_IOU = 0.3;
const VALUES_PER_ANCHOR = 17;

export interface Anchor {
  x: number;
  y: number;
}

export interface Detection {
  score: number;
  /** Frame-normalised box of the un-letterboxed image. */
  box: Box;
}

let cached: Anchor[] | null = null;

/** 512 anchors on the 16x16 map (two per cell), then 384 on the 8x8 map (six per cell). */
export function shortRangeAnchors(): Anchor[] {
  if (cached) return cached;
  const anchors: Anchor[] = [];
  let layer = 0;
  while (layer < STRIDES.length) {
    const stride = STRIDES[layer];
    let perCell = 0;
    let last = layer;
    while (last < STRIDES.length && STRIDES[last] === stride) {
      perCell += 2;
      last++;
    }
    const cells = Math.ceil(INPUT_SIZE / stride);
    for (let y = 0; y < cells; y++) {
      for (let x = 0; x < cells; x++) {
        for (let a = 0; a < perCell; a++) anchors.push({ x: (x + 0.5) / cells, y: (y + 0.5) / cells });
      }
    }
    layer = last;
  }
  cached = anchors;
  return anchors;
}

function iou(a: Box, b: Box): number {
  const x1 = Math.max(a.left, b.left);
  const y1 = Math.max(a.top, b.top);
  const x2 = Math.min(a.left + a.width, b.left + b.width);
  const y2 = Math.min(a.top + a.height, b.top + b.height);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const union = a.width * a.height + b.width * b.height - inter;
  return union <= 0 ? 0 : inter / union;
}

/** The letterbox that fits a `width` x `height` image into the square input: padding on each side, as fractions of the square. */
export function letterbox(width: number, height: number): { padX: number; padY: number } {
  if (width >= height) return { padX: 0, padY: (1 - height / width) / 2 };
  return { padX: (1 - width / height) / 2, padY: 0 };
}

/** `raw` is the model's `[1, 896, 17]` output flattened: score, then cx, cy, w, h and six keypoints, in input-pixel units. */
export function decode(raw: Float32Array, padX: number, padY: number): Detection[] {
  const anchors = shortRangeAnchors();
  const found: Detection[] = [];
  for (let i = 0; i < anchors.length; i++) {
    const o = i * VALUES_PER_ANCHOR;
    const logit = Math.min(100, Math.max(-100, raw[o]));
    const score = 1 / (1 + Math.exp(-logit));
    if (score < SCORE_THRESHOLD) continue;
    const cx = raw[o + 1] / INPUT_SIZE + anchors[i].x;
    const cy = raw[o + 2] / INPUT_SIZE + anchors[i].y;
    const w = raw[o + 3] / INPUT_SIZE;
    const h = raw[o + 4] / INPUT_SIZE;
    const sx = 1 - 2 * padX;
    const sy = 1 - 2 * padY;
    found.push({
      score,
      box: { left: (cx - w / 2 - padX) / sx, top: (cy - h / 2 - padY) / sy, width: w / sx, height: h / sy },
    });
  }
  found.sort((a, b) => b.score - a.score);
  const kept: Detection[] = [];
  for (const d of found) {
    if (kept.every((k) => iou(k.box, d.box) < NMS_IOU)) kept.push(d);
  }
  return kept;
}

/** Loads the graph model and runs it on video frames drawn, letterboxed, onto a 128x128 canvas. */
export class BlazeFaceModel {
  private readonly canvas: HTMLCanvasElement;
  private readonly ctx: CanvasRenderingContext2D;

  private constructor(private readonly model: GraphModel) {
    this.canvas = document.createElement("canvas");
    this.canvas.width = INPUT_SIZE;
    this.canvas.height = INPUT_SIZE;
    this.ctx = this.canvas.getContext("2d", { willReadFrequently: true })!;
  }

  static async load(modelUrl: string): Promise<BlazeFaceModel> {
    return new BlazeFaceModel(await loadGraphModel(modelUrl));
  }

  async detect(video: HTMLVideoElement): Promise<Detection[]> {
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (w === 0 || h === 0) return [];
    const { padX, padY } = letterbox(w, h);
    this.ctx.fillStyle = "#000";
    this.ctx.fillRect(0, 0, INPUT_SIZE, INPUT_SIZE);
    this.ctx.drawImage(video, padX * INPUT_SIZE, padY * INPUT_SIZE, (1 - 2 * padX) * INPUT_SIZE, (1 - 2 * padY) * INPUT_SIZE);
    const output = tf.tidy(() => {
      const input = tf.expandDims(tf.sub(tf.div(tf.cast(tf.browser.fromPixels(this.canvas), "float32"), 127.5), 1), 0);
      return this.model.execute(input) as tf.Tensor;
    });
    try {
      return decode((await output.data()) as Float32Array, padX, padY);
    } finally {
      output.dispose();
    }
  }

  dispose() {
    this.model.dispose();
  }
}
