import type { LumifaceClient } from "./client.ts";
import { configFromJson, DEFAULT_CONFIG, type LivenessConfig } from "./config.ts";
import { detectorFor, type ChallengeDetector } from "./detectors.ts";
import {
  type Box,
  clientError,
  isPresent,
  type Challenge,
  type FaceFlow,
  type FaceSession,
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

/** Grabs the most recent camera frame as a JPEG blob. */
export interface FrameCapturer {
  captureJpeg(): Promise<Blob>;
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

export function alignHint(s: FaceSignal, config: LivenessConfig, region: Box = FULL_FRAME): AlignHint | null {
  if (s.faceCount === 0 || !s.box) return "noFace";
  if (s.faceCount > 1) return "multipleFaces";
  const b = boxInRegion(s.box, region);
  if (b.width < config.minFaceWidthFraction) return "tooFar";
  if (b.width > config.maxFaceWidthFraction) return "tooClose";
  const dx = Math.abs(b.left + b.width / 2 - 0.5);
  const dy = Math.abs(b.top + b.height / 2 - 0.5);
  if (dx > config.centerTolerance || dy > config.centerTolerance) return "notCentered";
  if (Math.abs(s.yaw ?? 0) > config.neutralMaxYaw || Math.abs(s.pitch ?? 0) > config.neutralMaxPitch) {
    return "lookStraight";
  }
  return null;
}

type Listener = (state: LivenessState) => void;

/** Headless driver of one camera flow: observe `state`, feed it a source and a capturer. */
export abstract class FaceFlowController {
  private listeners = new Set<Listener>();
  private current: LivenessState = IDLE_STATE;
  protected disposed = false;

  /** What the preview shows of the frame; the view keeps it in step with its layout. See `visibleRegionFor`. */
  visibleRegion: Box = FULL_FRAME;

  constructor(
    readonly source: FaceSignalSource,
    readonly capturer: FrameCapturer,
  ) {}

  abstract readonly flow: FaceFlow;
  abstract get config(): LivenessConfig;
  abstract start(): Promise<void>;
  abstract cancel(): void;

  get state(): LivenessState {
    return this.current;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  protected set(patch: Partial<LivenessState>) {
    if (this.disposed) return;
    this.current = { ...this.current, ...patch };
    for (const l of this.listeners) l(this.current);
  }

  dispose() {
    this.disposed = true;
    this.listeners.clear();
  }
}

export interface FaceVerifyOptions {
  source: FaceSignalSource;
  capturer: FrameCapturer;
  client: LumifaceClient;
  /**
   * Fetches the session from your backend, which created it with the project key and fixed the
   * subject: return `sessionFromJson` of the server's `POST /v1/sessions` response. The browser
   * only ever holds the session's token.
   */
  sessionProvider: () => Promise<FaceSession>;
  /** "verify" (default) or "liveness"; the session decides once it arrives. */
  flow?: Exclude<FaceFlow, "enroll">;
  /** Overrides the project's client_config; omit to use what the server sends. */
  config?: LivenessConfig;
  clientInfo?: Record<string, unknown>;
  /** Frames streamed to the server per second of signal time. */
  streamFps?: number;
  random?: () => number;
}

/**
 * Drives one verification: session -> stream -> align -> challenges -> screen flash -> verdict.
 * Frames go to the server continuously while the flow runs; the events sent at each boundary
 * only tell the server where to look, it decides from its own frames and clock. A session the
 * backend created without a subject only proves liveness. When the server picked no turn and
 * `parallaxWhenNoTurn` is set, a client-only turn is appended (not reported). Timing comes from
 * `FaceSignal.tsMs`, so the controller is deterministic under test; a wall-clock watchdog only
 * guards a stalled stream.
 */
export class FaceVerifyController extends FaceFlowController {
  readonly client: LumifaceClient;
  readonly sessionProvider: () => Promise<FaceSession>;
  readonly clientInfo: Record<string, unknown>;
  private currentFlow: FaceFlow;
  private readonly explicitConfig: LivenessConfig | undefined;
  private readonly random: () => number;
  private currentConfig: LivenessConfig = DEFAULT_CONFIG;

  session: FaceSession | null = null;
  serverPlan: StreamPlan | null = null;
  private stream: VerifyStream | null = null;
  private plan: Challenge[] = [];
  private unsubscribe: (() => void) | null = null;
  private watchdog: ReturnType<typeof setTimeout> | null = null;
  private busy = false;
  private readonly streamFps: number;
  private lastFrameAt: number | null = null;
  private alignedSince: number | null = null;
  private challengeStartedAt: number | null = null;
  private lastFaceSeenAt: number | null = null;
  private settleUntil: number | null = null;
  private flashStartedAt: number | null = null;
  private flashDone = false;
  private detector: ChallengeDetector | null = null;

  constructor(options: FaceVerifyOptions) {
    super(options.source, options.capturer);
    this.client = options.client;
    this.sessionProvider = options.sessionProvider;
    this.currentFlow = options.flow ?? "verify";
    this.clientInfo = options.clientInfo ?? {};
    this.streamFps = options.streamFps ?? 8;
    this.explicitConfig = options.config;
    this.random = options.random ?? Math.random;
  }

  get flow(): FaceFlow {
    return this.currentFlow;
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
      this.stream = this.client.openStream(this.session, this.clientInfo);
      this.serverPlan = await this.stream.plan;
    } catch (e) {
      const code = e instanceof Error && "reasonCode" in e ? (e as { reasonCode: string }).reasonCode : "NETWORK_ERROR";
      this.finish(clientError(code, String(e)));
      return;
    }
    if (this.disposed) return;
    this.currentConfig = this.explicitConfig ?? configFromJson(this.serverPlan.clientConfig ?? this.session.clientConfig);
    this.plan = this.planChallenges(this.serverPlan.challenges);
    this.set({ ...IDLE_STATE, phase: "aligning", hint: "noFace", challengeCount: this.plan.length });
    this.watchdog = setTimeout(() => this.finish(clientError("TIMEOUT")), this.session.ttlSeconds * 1000);
    this.unsubscribe = this.source.subscribe((s) => this.onSignal(s));
  }

  cancel() {
    this.finish(clientError("CANCELLED"));
  }

  override dispose() {
    this.unsubscribe?.();
    if (this.watchdog) clearTimeout(this.watchdog);
    this.stream?.close();
    super.dispose();
  }

  private planChallenges(server: Challenge[]): Challenge[] {
    const hasTurn = server.some((c) => c === "turn_left" || c === "turn_right");
    if (hasTurn || !this.config.parallaxWhenNoTurn || this.config.parallaxMinShift <= 0) return server;
    return [...server, this.random() < 0.5 ? "turn_left" : "turn_right"];
  }

  private isServerChallenge(i: number) {
    return i < (this.serverPlan?.challenges.length ?? 0);
  }

  private finish(r: VerifyResult) {
    if (this.disposed || isDone(this.state)) return;
    this.unsubscribe?.();
    if (this.watchdog) clearTimeout(this.watchdog);
    if (this.state.phase !== "uploading") this.stream?.close();
    const result = this.session && !r.sessionId ? { ...r, sessionId: this.session.id } : r;
    this.set({ phase: result.ok ? "success" : "failed", result, hint: null });
  }

  /** One frame per 1/fps of signal time, whatever the phase, so the server sees the whole flow. */
  private streamFrame(s: FaceSignal) {
    if (!this.stream) return;
    if (this.lastFrameAt !== null && s.tsMs - this.lastFrameAt < 1000 / this.streamFps) return;
    this.lastFrameAt = s.tsMs;
    void this.capturer.captureJpeg().then((jpeg) => this.stream?.sendFrame(jpeg, s.tsMs)).catch(() => {});
  }


  private onSignal(s: FaceSignal) {
    if (this.busy || this.disposed || isDone(this.state)) return;
    if (isPresent(s)) this.lastFaceSeenAt = s.tsMs;
    this.streamFrame(s);
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

  private align(s: FaceSignal) {
    const hint = alignHint(s, this.config, this.visibleRegion);
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

  private startChallenge(i: number, s: FaceSignal) {
    const c = this.plan[i];
    this.detector = detectorFor(c, this.config);
    this.detector.feed(s);
    this.challengeStartedAt = s.tsMs;
    this.settleUntil = null;
    this.set({ phase: "challenge", challenge: c, challengeIndex: i, hint: null });
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
      const next = this.state.challengeIndex + 1;
      if (next < this.plan.length) {
        this.startChallenge(next, s);
        return;
      }
      const hint = alignHint(s, this.config, this.visibleRegion);
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
    if (this.detector!.feed(s)) {
      const i = this.state.challengeIndex;
      if (this.isServerChallenge(i)) this.stream?.event("challenge_done", s.tsMs, i);
      this.settleUntil = s.tsMs + this.config.settleAfterChallengeMs;
    }
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

export interface FaceEnrollOptions {
  source: FaceSignalSource;
  capturer: FrameCapturer;
  client: LumifaceClient;
  /**
   * Fetches a single-use enrol token from your backend (`POST /v1/subjects/tokens` there); the
   * token names the subject, so the browser sends only the photo.
   */
  enrolTokenProvider: () => Promise<string>;
  config?: LivenessConfig;
  timeoutMs?: number;
}

/** Aligns the face, captures one frontal frame and enrols it. */
export class FaceEnrollController extends FaceFlowController {
  readonly flow: FaceFlow = "enroll";
  readonly config: LivenessConfig;
  private readonly options: FaceEnrollOptions;
  private unsubscribe: (() => void) | null = null;
  private watchdog: ReturnType<typeof setTimeout> | null = null;
  private busy = false;
  private alignedSince: number | null = null;

  constructor(options: FaceEnrollOptions) {
    super(options.source, options.capturer);
    this.options = options;
    this.config = options.config ?? DEFAULT_CONFIG;
  }

  async start(): Promise<void> {
    if (this.state.phase !== "idle") return;
    this.set({ phase: "aligning", hint: "noFace" });
    this.watchdog = setTimeout(() => this.finish(clientError("TIMEOUT")), this.options.timeoutMs ?? 60000);
    this.unsubscribe = this.source.subscribe((s) => this.onSignal(s));
  }

  cancel() {
    this.finish(clientError("CANCELLED"));
  }

  override dispose() {
    this.unsubscribe?.();
    if (this.watchdog) clearTimeout(this.watchdog);
    super.dispose();
  }

  private onSignal(s: FaceSignal) {
    if (this.busy || this.disposed || this.state.phase !== "aligning") return;
    const hint = alignHint(s, this.config, this.visibleRegion);
    if (hint) {
      this.alignedSince = null;
      this.set({ hint });
      return;
    }
    this.alignedSince ??= s.tsMs;
    this.set({ hint: "holdStill" });
    if (s.tsMs - this.alignedSince < this.config.alignHoldMs) return;
    this.busy = true;
    this.unsubscribe?.();
    this.set({ phase: "uploading", hint: null });
    void this.submit();
  }

  private async submit() {
    try {
      const photo = await this.capturer.captureJpeg();
      const enrolToken = await this.options.enrolTokenProvider();
      const subject = await this.options.client.enroll({ photo, enrolToken });
      this.finish({ ...clientError("OK"), ok: true, mode: "enroll", subject });
    } catch (e) {
      const code = e instanceof Error && "reasonCode" in e ? (e as { reasonCode: string }).reasonCode : "NETWORK_ERROR";
      this.finish({ ...clientError(code, String(e)), mode: "enroll" });
    }
  }

  private finish(r: VerifyResult) {
    if (this.disposed || isDone(this.state)) return;
    this.unsubscribe?.();
    if (this.watchdog) clearTimeout(this.watchdog);
    this.set({ phase: r.ok ? "success" : "failed", result: r, hint: null });
  }
}
