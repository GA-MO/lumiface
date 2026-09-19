import type { LumifaceClient } from "./client.ts";
import { configFromJson, DEFAULT_CONFIG, type LivenessConfig } from "./config.ts";
import { detectorFor, FaceMoveDetector, type ChallengeDetector } from "./detectors.ts";
import {
  type Box,
  clientError,
  isPresent,
  type Challenge,
  type FaceFlow,
  type FaceSession,
  type StreamFormat,
  type StreamPlan,
  type VerifyStream,
  type FaceSignal,
  type VerifyResult,
} from "./types.ts";

export type LivenessPhase = "idle" | "starting" | "aligning" | "challenge" | "flash" | "uploading" | "success" | "failed";

export type AlignHint = "noFace" | "multipleFaces" | "tooFar" | "tooClose" | "notCentered" | "lookStraight" | "holdStill";

export interface LivenessState {
  phase: LivenessPhase;
  hint: AlignHint | null;
  challenge: Challenge | null;
  challengeIndex: number;
  challengeCount: number;
  /** Hex colour (no '#') the UI must fill the screen with while `phase` is "flash". */
  flashColor: string | null;
  flashIndex: number;
  result: VerifyResult | null;
  /** The oval a `face_move` challenge asks the face to fill, as fractions of the preview; the guide
   *  draws it instead of the theme's shape once set. */
  target: Box | null;
}

export const IDLE_STATE: LivenessState = {
  phase: "idle",
  hint: null,
  challenge: null,
  challengeIndex: 0,
  challengeCount: 0,
  flashColor: null,
  flashIndex: 0,
  result: null,
  target: null,
};

export function isDone(s: LivenessState): boolean {
  return s.phase === "success" || s.phase === "failed";
}

/** 0..1 for a progress bar, null while idle or failed. */
export function progressOf(s: LivenessState): number | null {
  switch (s.phase) {
    case "aligning":
      return 0;
    case "challenge":
      return s.challengeCount === 0 ? 0 : (s.challengeIndex + 0.5) / (s.challengeCount + 1);
    case "flash":
    case "uploading":
      return s.challengeCount / (s.challengeCount + 1);
    case "success":
      return 1;
    default:
      return null;
  }
}

/** Streams face observations from a camera. */
export interface FaceSignalSource {
  subscribe(listener: (s: FaceSignal) => void): () => void;
}

/** Records the camera while a verification runs and hands out chunks as they are cut; `tsMs` is the
 *  device time (the signal clock) of the chunk's first frame. The server decodes the stream itself. */
export interface VideoRecorder {
  readonly format: StreamFormat;
  start(onChunk: (data: Blob | ArrayBuffer, tsMs: number) => void): void;
  stop(): void;
}

/** The whole camera frame, in frame-normalised coordinates. */
export const FULL_FRAME: Box = { left: 0, top: 0, width: 1, height: 1 };

/**
 * The part of a `videoAspect` frame that `object-fit: cover` shows in a `containerAspect` box.
 * Alignment is judged inside this region so "move closer" means what the person sees on screen,
 * not the raw landscape frame a webcam delivers behind a portrait preview.
 */
export function visibleRegionFor(videoAspect: number, containerAspect: number): Box {
  if (!(videoAspect > 0) || !(containerAspect > 0) || videoAspect === containerAspect) return FULL_FRAME;
  if (videoAspect > containerAspect) {
    const width = containerAspect / videoAspect;
    return { left: (1 - width) / 2, top: 0, width, height: 1 };
  }
  const height = videoAspect / containerAspect;
  return { left: 0, top: (1 - height) / 2, width: 1, height };
}

/** Re-expresses a frame-normalised box relative to `region`. */
export function boxInRegion(b: Box, region: Box): Box {
  return {
    left: (b.left - region.left) / region.width,
    top: (b.top - region.top) / region.height,
    width: b.width / region.width,
    height: b.height / region.height,
  };
}

/** `maxWidth` overrides `maxFaceWidthFraction`: the controller passes the oval's start width so the
 *  walk into the oval always begins from where the person held still, whatever the frame's aspect. */
export function alignHint(s: FaceSignal, config: LivenessConfig, region: Box = FULL_FRAME, maxWidth = config.maxFaceWidthFraction): AlignHint | null {
  if (s.faceCount === 0 || !s.box) return "noFace";
  if (s.faceCount > 1) return "multipleFaces";
  const b = boxInRegion(s.box, region);
  if (b.width < config.minFaceWidthFraction) return "tooFar";
  if (b.width > maxWidth) return "tooClose";
  const dx = Math.abs(b.left + b.width / 2 - 0.5);
  const dy = Math.abs(b.top + b.height / 2 - 0.5);
  if (dx > config.centerTolerance || dy > config.centerTolerance) return "notCentered";
  return frontalHint(s, config);
}

/** After the oval the face is close by design: only its presence and (where the detector reports angles) its pose still matter. */
export function frontalHint(s: FaceSignal, config: LivenessConfig): AlignHint | null {
  if (s.faceCount === 0 || !s.box) return "noFace";
  if (s.faceCount > 1) return "multipleFaces";
  if (Math.abs(s.yaw ?? 0) > config.neutralMaxYaw || Math.abs(s.pitch ?? 0) > config.neutralMaxPitch) {
    return "lookStraight";
  }
  return null;
}

type Listener = (state: LivenessState) => void;

export interface FaceVerifyOptions {
  source: FaceSignalSource;
  /** Records the camera for the server; `BlazeFaceSource` is one. */
  recorder: VideoRecorder;
  client: LumifaceClient;
  /**
   * Fetches the session from your backend, which created it with the project key and fixed who is
   * verified (the reference photo): return `sessionFromJson` of the server's `POST /v1/sessions`
   * response. The browser only ever holds the session's token.
   */
  sessionProvider: () => Promise<FaceSession>;
  /** "verify" (default) or "liveness"; the session decides once it arrives. */
  flow?: FaceFlow;
  /** Overrides the project's client_config; omit to use what the server sends. */
  config?: LivenessConfig;
  clientInfo?: Record<string, unknown>;
}

/**
 * Headless driver of one verification, owning no DOM: observe `state`, feed it a source and a
 * recorder. Session -> stream -> align -> the oval -> screen flash -> verdict.
 * The recorder runs from the plan to the verdict and its chunks go to the server as they are cut;
 * the events sent at each boundary only tell the server where to look, it decides from the frames
 * it decodes and its own clock. A session the backend created without a reference photo only
 * proves liveness. Timing comes from `FaceSignal.tsMs`, so the controller is deterministic under
 * test; a wall-clock watchdog only guards a stalled stream.
 */
export class FaceVerifyController {
  private listeners = new Set<Listener>();
  private current: LivenessState = IDLE_STATE;
  private disposed = false;

  /** What the preview shows of the frame; the view keeps it in step with its layout. See `visibleRegionFor`. */
  visibleRegion: Box = FULL_FRAME;

  /** The camera frame's width over its height; the view keeps it in step with the source. */
  frameAspect = 4 / 3;

  readonly source: FaceSignalSource;
  readonly client: LumifaceClient;
  readonly recorder: VideoRecorder;
  readonly sessionProvider: () => Promise<FaceSession>;
  readonly clientInfo: Record<string, unknown>;
  private currentFlow: FaceFlow;
  private readonly explicitConfig: LivenessConfig | undefined;
  private currentConfig: LivenessConfig = DEFAULT_CONFIG;

  session: FaceSession | null = null;
  serverPlan: StreamPlan | null = null;
  private stream: VerifyStream | null = null;
  private plan: Challenge[] = [];
  private unsubscribe: (() => void) | null = null;
  private watchdog: ReturnType<typeof setTimeout> | null = null;
  private busy = false;
  private recording = false;
  private alignedSince: number | null = null;
  private challengeStartedAt: number | null = null;
  private lastFaceSeenAt: number | null = null;
  private settleUntil: number | null = null;
  private doneReported = false;
  private flashStartedAt: number | null = null;
  private flashDone = false;
  private detector: ChallengeDetector | null = null;

  constructor(options: FaceVerifyOptions) {
    this.source = options.source;
    this.client = options.client;
    this.recorder = options.recorder;
    this.sessionProvider = options.sessionProvider;
    this.currentFlow = options.flow ?? "verify";
    this.clientInfo = options.clientInfo ?? {};
    this.explicitConfig = options.config;
  }

  get flow(): FaceFlow {
    return this.currentFlow;
  }

  get state(): LivenessState {
    return this.current;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private set(patch: Partial<LivenessState>) {
    if (this.disposed) return;
    this.current = { ...this.current, ...patch };
    for (const l of this.listeners) l(this.current);
  }

  get config(): LivenessConfig {
    return this.currentConfig;
  }

  async start(): Promise<void> {
    if (this.state.phase !== "idle") return;
    this.set({ phase: "starting" });
    try {
      this.session = await this.sessionProvider();
    } catch (e) {
      this.finish(clientError("NETWORK_ERROR", String(e)));
      return;
    }
    if (this.disposed) return;
    this.currentFlow = this.session.mode === "liveness" ? "liveness" : "verify";
    try {
      this.stream = this.client.openStream(this.session, this.clientInfo, this.recorder.format);
      this.serverPlan = await this.stream.plan;
    } catch (e) {
      const code = e instanceof Error && "reasonCode" in e ? (e as { reasonCode: string }).reasonCode : "NETWORK_ERROR";
      this.finish(clientError(code, String(e)));
      return;
    }
    if (this.disposed) return;
    this.currentConfig = this.explicitConfig ?? configFromJson(this.serverPlan.clientConfig ?? this.session.clientConfig);
    this.plan = this.serverPlan.challenges;
    this.set({ ...IDLE_STATE, phase: "aligning", hint: "noFace", challengeCount: this.plan.length });
    this.watchdog = setTimeout(() => this.finish(clientError("TIMEOUT")), this.session.ttlSeconds * 1000);
    this.recording = true;
    this.recorder.start((data, tsMs) => this.stream?.sendChunk(data, tsMs));
    this.unsubscribe = this.source.subscribe((s) => this.onSignal(s));
  }

  cancel() {
    this.finish(clientError("CANCELLED"));
  }

  dispose() {
    this.unsubscribe?.();
    this.stopRecording();
    if (this.watchdog) clearTimeout(this.watchdog);
    this.stream?.close();
    this.disposed = true;
    this.listeners.clear();
  }

  private stopRecording() {
    if (!this.recording) return;
    this.recording = false;
    this.recorder.stop();
  }

  private finish(r: VerifyResult) {
    if (this.disposed || isDone(this.state)) return;
    this.unsubscribe?.();
    this.stopRecording();
    if (this.watchdog) clearTimeout(this.watchdog);
    if (this.state.phase !== "uploading") this.stream?.close();
    const result = this.session && !r.sessionId ? { ...r, sessionId: this.session.id } : r;
    this.set({ phase: result.ok ? "success" : "failed", result, hint: null });
  }

  private onSignal(s: FaceSignal) {
    if (this.busy || this.disposed || isDone(this.state)) return;
    if (isPresent(s)) this.lastFaceSeenAt = s.tsMs;
    switch (this.state.phase) {
      case "aligning":
        this.align(s);
        break;
      case "challenge":
        this.challenge(s);
        break;
      case "flash":
        this.flash(s);
        break;
    }
  }

  /** The widest a face may be at alignment: the oval's start, when the plan has one. */
  private alignMaxWidth(): number {
    const oval = this.ovalBox();
    const limit = this.config.maxFaceWidthFraction;
    return oval ? Math.min(limit, boxInRegion(oval, this.visibleRegion).width * this.config.moveStartMaxRatio) : limit;
  }

  private align(s: FaceSignal) {
    const hint = alignHint(s, this.config, this.visibleRegion, this.alignMaxWidth());
    if (hint) {
      this.alignedSince = null;
      this.set({ hint });
      return;
    }
    this.alignedSince ??= s.tsMs;
    this.set({ hint: "holdStill" });
    if (s.tsMs - this.alignedSince >= this.config.alignHoldMs) {
      this.stream?.event("aligned", s.tsMs);
      this.startChallenge(0, s);
    }
  }

  /** The plan's oval in frame-normalised coordinates. Its width is a fraction of the frame's shorter
   *  side (faces scale with it whatever the orientation), so both fractions depend on the aspect. */
  private ovalBox(): Box | null {
    const o = this.serverPlan?.oval;
    if (!o) return null;
    const landscape = this.frameAspect > 1;
    const width = landscape ? o.width / this.frameAspect : o.width;
    const height = landscape ? o.width * o.heightRatio : o.width * o.heightRatio * this.frameAspect;
    return { left: o.cx - width / 2, top: o.cy - height / 2, width, height };
  }

  private startChallenge(i: number, s: FaceSignal) {
    const c = this.plan[i];
    const oval = c === "face_move" ? this.ovalBox() : null;
    this.detector = detectorFor(c, this.config, oval ?? undefined);
    this.detector.feed(s);
    this.challengeStartedAt = s.tsMs;
    this.settleUntil = null;
    this.doneReported = false;
    this.set({
      phase: "challenge",
      challenge: c,
      challengeIndex: i,
      hint: null,
      ...(oval ? { target: boxInRegion(oval, this.visibleRegion) } : {}),
    });
  }

  private faceLost(s: FaceSignal): boolean {
    if (isPresent(s)) return false;
    if (this.lastFaceSeenAt !== null && s.tsMs - this.lastFaceSeenAt > this.config.faceLostGraceMs) {
      this.finish(clientError("FACE_LOST"));
    }
    return true;
  }

  private challenge(s: FaceSignal) {
    if (this.faceLost(s)) return;
    if (s.faceCount > 1) return;
    if (s.tsMs - (this.challengeStartedAt ?? 0) > this.config.challengeTimeoutMs) {
      this.finish(clientError("TIMEOUT"));
      return;
    }
    if (this.settleUntil !== null) {
      if (s.tsMs < this.settleUntil) return;
      const i = this.state.challengeIndex;
      if (!this.doneReported) {
        this.doneReported = true;
        this.stream?.event("challenge_done", s.tsMs, i);
      }
      const next = i + 1;
      if (next < this.plan.length) {
        this.startChallenge(next, s);
        return;
      }
      const hint = frontalHint(s, this.config);
      if (hint) {
        this.set({ hint });
        return;
      }
      if (!this.flashDone && this.serverPlan!.flashColors.length > 0) {
        this.startFlash(0, s.tsMs);
        return;
      }
      this.guard(() => this.upload());
      return;
    }
    // The window closes after the settle, so the frames with the face at rest in the oval are inside it.
    if (this.detector!.feed(s)) this.settleUntil = s.tsMs + this.config.settleAfterChallengeMs;
    else if (this.detector instanceof FaceMoveDetector) this.set({ hint: this.detector.hint });
  }

  private startFlash(i: number, tsMs: number) {
    this.flashStartedAt = tsMs;
    this.stream?.event("flash", tsMs, i);
    this.set({ phase: "flash", flashIndex: i, flashColor: this.serverPlan!.flashColors[i], hint: null });
  }

  private flash(s: FaceSignal) {
    if (this.faceLost(s)) return;
    if (s.tsMs - (this.flashStartedAt ?? 0) < this.serverPlan!.flashHoldMs) return;
    const i = this.state.flashIndex;
    if (i + 1 < this.serverPlan!.flashColors.length) {
      this.startFlash(i + 1, s.tsMs);
      return;
    }
    this.stream?.event("flash_end", s.tsMs);
    this.flashDone = true;
    this.challengeStartedAt = s.tsMs;
    this.settleUntil = s.tsMs + this.config.settleAfterFlashMs;
    this.set({ phase: "challenge", flashColor: null });
  }

  private async upload() {
    this.unsubscribe?.();
    this.set({ phase: "uploading", hint: null });
    this.stopRecording();
    try {
      this.finish(await this.stream!.end());
    } catch (e) {
      this.finish(clientError("NETWORK_ERROR", String(e)));
    }
  }

  private guard(body: () => Promise<void>) {
    this.busy = true;
    body()
      .catch((e) => this.finish(clientError("CAPTURE_ERROR", String(e))))
      .finally(() => {
        this.busy = false;
      });
  }
}
