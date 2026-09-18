export type Challenge = "blink" | "turn_left" | "turn_right" | "smile" | "nod";

export type FaceFlow = "verify" | "liveness" | "enroll";

export interface Point {
  x: number;
  y: number;
}

/** Normalised (0..1) box in the upright, un-mirrored camera image. */
export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * One observation of the face. Angles are degrees; positive yaw is the
 * user's own left. Everything but `tsMs` and `faceCount` is null without a face.
 */
export interface FaceSignal {
  tsMs: number;
  faceCount: number;
  box: Box | null;
  eyeOpenLeft: number | null;
  eyeOpenRight: number | null;
  smile: number | null;
  yaw: number | null;
  pitch: number | null;
  nose: Point | null;
  leftEye: Point | null;
  rightEye: Point | null;
}

export function noFace(tsMs: number): FaceSignal {
  return {
    tsMs,
    faceCount: 0,
    box: null,
    eyeOpenLeft: null,
    eyeOpenRight: null,
    smile: null,
    yaw: null,
    pitch: null,
    nose: null,
    leftEye: null,
    rightEye: null,
  };
}

export function isPresent(s: FaceSignal): boolean {
  return s.faceCount === 1 && s.box !== null;
}

export function eyeOpen(s: FaceSignal): number | null {
  if (s.eyeOpenLeft === null || s.eyeOpenRight === null) return null;
  return (s.eyeOpenLeft + s.eyeOpenRight) / 2;
}

/**
 * Horizontal offset of the nose from the eye midpoint in inter-eye units.
 * Constant when a flat picture rotates, shifts with yaw on a real head.
 */
export function noseParallax(s: FaceSignal): number | null {
  if (!s.nose || !s.leftEye || !s.rightEye) return null;
  const dist = Math.abs(s.rightEye.x - s.leftEye.x);
  if (dist < 1e-4) return null;
  return (s.nose.x - (s.leftEye.x + s.rightEye.x) / 2) / dist;
}

/** What the backend hands the browser. The plan (challenges, colours) only arrives over the stream. */
export interface FaceSession {
  id: string;
  /** Bearer secret good for this session's stream only. */
  token: string;
  mode: "verify" | "liveness";
  purpose: string;
  ttlSeconds: number;
  clientConfig: Record<string, unknown> | null;
}

/** The server's first message on the stream: what to do, decided server-side for this session. */
export interface StreamPlan {
  challenges: Challenge[];
  /** Hex colours without '#', in order. Empty when the server disabled the flash. */
  flashColors: string[];
  flashHoldMs: number;
  clientConfig: Record<string, unknown> | null;
}

export type StreamEventName = "aligned" | "challenge_done" | "flash" | "flash_end";

/**
 * One verification in flight: frames go up continuously, events tell the server where to look,
 * `end()` resolves with the verdict. The server clocks everything itself.
 */
export interface VerifyStream {
  readonly plan: Promise<StreamPlan>;
  /** Queues a frame; frames are dropped rather than buffered when the socket is congested. */
  sendFrame(jpeg: Blob, tsMs: number): void;
  event(name: StreamEventName, tsMs: number, index?: number): void;
  end(): Promise<VerifyResult>;
  /** Abandons the stream; the server records the session as spent. */
  close(): void;
}

export interface VerifyScores {
  match: number | null;
  spoof: number | null;
  consistency: number | null;
}

export interface Subject {
  externalId: string;
  name: string;
  enrollSpoofScore: number;
  /** ISO time when the server drops the embedding; null keeps it until deleted. */
  expiresAt: string | null;
}

export interface VerifyResult {
  ok: boolean;
  mode: string;
  reasonCode: string;
  scores: VerifyScores;
  verificationId: number | null;
  /** The session this result belongs to; hand it to your backend, which reads the outcome with `GET /v1/sessions/{id}`. */
  sessionId?: string;
  subject?: Subject;
  message?: string;
}

export function clientError(code: string, message?: string): VerifyResult {
  return {
    ok: false,
    mode: "verify",
    reasonCode: code,
    scores: { match: null, spoof: null, consistency: null },
    verificationId: null,
    message,
  };
}

export interface VerificationRecord {
  id: number;
  sessionId: string;
  subjectId: string | null;
  purpose: string;
  ok: boolean;
  reasonCode: string;
  createdAt: string;
  scores: VerifyScores;
}

export interface ProjectPolicy {
  project: string;
  preset: string;
  overrides: Record<string, unknown>;
  effective: Record<string, unknown> & { client: Record<string, unknown> };
}

export interface PolicyPreset {
  name: string;
  summary: string;
  overrides: Record<string, unknown>;
}

export class LumifaceError extends Error {
  constructor(
    public readonly reasonCode: string,
    public readonly details?: unknown,
  ) {
    super(reasonCode);
    this.name = "LumifaceError";
  }
}
