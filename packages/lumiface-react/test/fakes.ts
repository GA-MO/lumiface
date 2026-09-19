import { LumifaceClient } from "../src/client.ts";
import { LumifaceError } from "../src/types.ts";
import type { FaceSignalSource, VideoRecorder } from "../src/controller.ts";
import type { Challenge, FaceSession, FaceSignal, OvalTarget, StreamEventName, StreamFormat, VerifyResult, VerifyStream } from "../src/types.ts";

export class FakeSource implements FaceSignalSource, VideoRecorder {
  private listeners = new Set<(s: FaceSignal) => void>();
  readonly format: StreamFormat = "webm";
  /** The recorder's state as the controller drove it: started, then stopped. */
  recording = false;
  recordings = 0;
  private onChunk: ((data: Blob, tsMs: number) => void) | null = null;

  subscribe(listener: (s: FaceSignal) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  emit(s: FaceSignal) {
    for (const l of this.listeners) l(s);
  }

  start(onChunk: (data: Blob, tsMs: number) => void) {
    this.recording = true;
    this.recordings++;
    this.onChunk = onChunk;
  }

  stop() {
    this.recording = false;
    this.onChunk = null;
  }

  /** A chunk the recorder cut at `tsMs`; delivered only while recording, like MediaRecorder. */
  chunk(tsMs: number) {
    this.onChunk?.(new Blob([new Uint8Array([0x1a, 0x45, tsMs & 0xff])]), tsMs);
  }
}

export class FakeClient extends LumifaceClient {
  response: VerifyResult | null = null;
  /** What the controller streamed: chunk timestamps and events, in order, and the hello's format. */
  sentChunks: number[] = [];
  format: StreamFormat | null = null;
  sentEvents: { name: StreamEventName; ts: number; index?: number }[] = [];
  ended = false;
  closed = false;
  planError: string | null = null;
  lastReference: boolean | undefined;
  lastPurpose = "";
  sessionConfig: Record<string, unknown> | null = null;

  constructor(
    readonly challenges: Challenge[],
    readonly flashColors: string[] = [],
    readonly oval: OvalTarget | null = null,
  ) {
    super({ baseUrl: "http://x" });
  }

  /** Stands in for the app's backend call; `reference: false` = a session without a reference photo (liveness). */
  createSession = async (options: { reference?: boolean; purpose?: string } = {}): Promise<FaceSession> => {
    const reference = options.reference ?? true;
    this.lastReference = reference;
    this.lastPurpose = options.purpose ?? "";
    return {
      id: "s1",
      token: "tok",
      mode: reference ? "verify" : "liveness",
      purpose: this.lastPurpose,
      ttlSeconds: 60,
      clientConfig: null,
    };
  };

  override openStream(_session: FaceSession, _clientInfo: Record<string, unknown> = {}, format: StreamFormat = "jpeg"): VerifyStream {
    this.format = format;
    const plan = this.planError
      ? Promise.reject(new LumifaceError(this.planError))
      : Promise.resolve({ challenges: this.challenges, flashColors: this.flashColors, flashHoldMs: 450, clientConfig: this.sessionConfig, oval: this.oval });
    plan.catch(() => {});
    return {
      plan,
      sendChunk: (_data, ts) => {
        this.sentChunks.push(ts);
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
}

/** A well-framed face, `width` of the frame wide and centred; `yaw`/`pitch` as a detector with angles would report. */
export function neutral(ts: number, o: { yaw?: number; pitch?: number; width?: number } = {}): FaceSignal {
  const { yaw = 0, pitch = 0, width = 0.45 } = o;
  const height = width * 1.125;
  return { tsMs: ts, faceCount: 1, box: { left: 0.5 - width / 2, top: 0.45 - height / 2, width, height }, yaw, pitch };
}

export const pump = () => new Promise<void>((r) => setTimeout(r, 0));
