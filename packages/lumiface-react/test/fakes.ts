import { LumifaceClient } from "../src/client.ts";
import { LumifaceError } from "../src/types.ts";
import type { FaceSignalSource, FrameCapturer } from "../src/controller.ts";
import type { Challenge, FaceSession, FaceSignal, StreamEventName, Subject, VerifyResult, VerifyStream } from "../src/types.ts";

export class FakeSource implements FaceSignalSource, FrameCapturer {
  private listeners = new Set<(s: FaceSignal) => void>();
  captures = 0;

  subscribe(listener: (s: FaceSignal) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  emit(s: FaceSignal) {
    for (const l of this.listeners) l(s);
  }

  async captureJpeg(): Promise<Blob> {
    this.captures++;
    return new Blob([new Uint8Array([0xff, 0xd8, this.captures])], { type: "image/jpeg" });
  }
}

export class FakeClient extends LumifaceClient {
  response: VerifyResult | null = null;
  /** What the controller streamed: frame timestamps and events, in order. */
  sentFrames: number[] = [];
  sentEvents: { name: StreamEventName; ts: number; index?: number }[] = [];
  ended = false;
  closed = false;
  planError: string | null = null;
  lastSubjectId: string | null | undefined;
  lastPurpose = "";
  sessionConfig: Record<string, unknown> | null = null;
  enrollCalls = 0;

  constructor(
    readonly challenges: Challenge[],
    readonly flashColors: string[] = [],
  ) {
    super({ baseUrl: "http://x" });
  }

  /** Stands in for the app's backend call; `subjectId: null` = liveness session. */
  createSession = async (options: { subjectId?: string | null; purpose?: string } = { subjectId: "E001" }): Promise<FaceSession> => {
    this.lastSubjectId = options.subjectId;
    this.lastPurpose = options.purpose ?? "";
    return {
      id: "s1",
      token: "tok",
      mode: options.subjectId ? "verify" : "liveness",
      purpose: this.lastPurpose,
      ttlSeconds: 60,
      clientConfig: null,
    };
  };

  override openStream(): VerifyStream {
    const plan = this.planError
      ? Promise.reject(new LumifaceError(this.planError))
      : Promise.resolve({ challenges: this.challenges, flashColors: this.flashColors, flashHoldMs: 450, clientConfig: this.sessionConfig });
    plan.catch(() => {});
    return {
      plan,
      sendFrame: (_jpeg, ts) => {
        this.sentFrames.push(ts);
      },
      event: (name, ts, index) => {
        this.sentEvents.push({ name, ts, ...(index === undefined ? {} : { index }) });
      },
      end: async () => {
        this.ended = true;
        return this.response ?? { ok: true, mode: "verify", reasonCode: "OK", scores: { match: 0.9, spoof: 0.9, consistency: 0.9 }, verificationId: 1 };
      },
      close: () => {
        this.closed = true;
      },
    };
  }

  /** The fake token names the subject, like the real one does server-side: `tok:<id>:<name>`. */
  override async enroll(options: { photo: Blob; enrolToken: string }): Promise<Subject> {
    this.enrollCalls++;
    const [, externalId = "", name = ""] = options.enrolToken.split(":");
    if (externalId === "REJECT") throw new LumifaceError("POSE_NOT_FRONTAL");
    return { externalId, name, enrollSpoofScore: 0.9, expiresAt: null };
  }
}

/** A well-framed face with landmarks; the nose sits in front of the eye plane so it shifts with yaw unless `flat`. */
export function neutral(ts: number, o: { eye?: number; smile?: number; yaw?: number; pitch?: number; flat?: boolean } = {}): FaceSignal {
  const { eye = 0.95, smile = 0.05, yaw = 0, pitch = 0, flat = false } = o;
  const cx = 0.5, eyeY = 0.45, noseY = 0.55, halfEye = 0.08;
  const rad = (yaw * Math.PI) / 180;
  const half = halfEye * Math.cos(rad);
  const noseShift = flat ? 0 : 0.35 * halfEye * 2 * Math.sin(rad);
  return {
    tsMs: ts,
    faceCount: 1,
    box: { left: 0.3, top: 0.3, width: 0.4, height: 0.45 },
    eyeOpenLeft: eye,
    eyeOpenRight: eye,
    smile,
    yaw,
    pitch,
    nose: { x: cx + noseShift, y: noseY },
    leftEye: { x: cx - half, y: eyeY },
    rightEye: { x: cx + half, y: eyeY },
  };
}

export const pump = () => new Promise<void>((r) => setTimeout(r, 0));
