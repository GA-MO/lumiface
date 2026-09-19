/** The one challenge: move closer until the face fills the oval the server chose . */
export type Challenge = "face_move";

export type FaceFlow = "verify" | "liveness" | "enroll";

/** Normalised (0..1) box in the upright, un-mirrored camera image. */
export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * One observation of the face: the largest box the detector found and, when the detector reports
 * them (Apple Vision does, BlazeFace does not), the head angles in degrees. `box` is null without a face.
 */
export interface FaceSignal {
  tsMs: number;
  faceCount: number;
  box: Box | null;
  yaw: number | null;
  pitch: number | null;
}

export function noFace(tsMs: number): FaceSignal {
  return { tsMs, faceCount: 0, box: null, yaw: null, pitch: null };
}

export function isPresent(s: FaceSignal): boolean {
  return s.faceCount === 1 && s.box !== null;
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
/** The oval a `face_move` challenge asks the face to fill: `cx`, `cy` are fractions of the camera
 *  frame, `width` a fraction of the frame's shorter side, `heightRatio` the oval's height over its width. */
export interface OvalTarget {
  cx: number;
  cy: number;
  width: number;
  heightRatio: number;
}

export interface StreamPlan {
  challenges: Challenge[];
  /** Hex colours without '#', in order. Empty when the server disabled the flash. */
  flashColors: string[];
  flashHoldMs: number;
  clientConfig: Record<string, unknown> | null;
  /** Present when the plan includes `face_move`. */
  oval: OvalTarget | null;
}

export type StreamEventName = "aligned" | "challenge_done" | "flash" | "flash_end";

/** What each binary message on the stream carries: a recorder's video chunk (`webm` from MediaRecorder,
 *  `mp4` from Safari's, `h264` one access unit per message) or a single JPEG frame. */
export type StreamFormat = "jpeg" | "webm" | "mp4" | "h264";

/**
 * One verification in flight: video chunks go up as they are recorded, events tell the server
 * where to look, `end()` resolves with the verdict. The server decodes the video into frames and
 * clocks everything itself.
 */
export interface VerifyStream {
  readonly plan: Promise<StreamPlan>;
  /** Queues a chunk stamped with the device time of its first frame; chunks are dropped rather than
   *  buffered when the socket is congested. */
  sendChunk(data: Blob | ArrayBuffer, tsMs: number): void;
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
