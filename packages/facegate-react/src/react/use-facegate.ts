import { useCallback, useEffect, useRef, useState } from "react";

import type { FacegateClient } from "../client.ts";
import type { LivenessConfig } from "../config.ts";
import { FaceEnrollController, FaceVerifyController, IDLE_STATE, type FaceFlowController, type LivenessState } from "../controller.ts";
import { MediaPipeSource, type MediaPipeSourceOptions } from "../mediapipe-source.ts";
import type { FaceFlow, FaceSignal, VerifyResult } from "../types.ts";

export interface UseFacegateOptions {
  client: FacegateClient;
  /** Defaults to "verify" with a subjectId and "liveness" without. */
  flow?: FaceFlow;
  subjectId?: string | null;
  purpose?: string;
  subjectName?: string;
  replaceEnrollment?: boolean;
  config?: LivenessConfig;
  clientInfo?: Record<string, unknown>;
  camera?: MediaPipeSourceOptions;
  autoStart?: boolean;
  onResult?: (result: VerifyResult) => void;
  /** Push screen brightness up / restore it around the flash step. */
  onFlashChanged?: (flashing: boolean) => void;
}

export interface FacegateHandle {
  state: LivenessState;
  signal: FaceSignal | null;
  flow: FaceFlow;
  ready: boolean;
  error: Error | null;
  controller: FaceFlowController | null;
  source: MediaPipeSource | null;
  /** Attach to a container; the camera `<video>` is mounted inside it. */
  mountVideo: (el: HTMLElement | null) => void;
  start: () => Promise<void>;
  cancel: () => void;
}

function resolveFlow(options: UseFacegateOptions): FaceFlow {
  return options.flow ?? (options.subjectId ? "verify" : "liveness");
}

/** Camera + controller lifecycle for one flow. Re-runs when `client`, `flow`, `subjectId` or `purpose` change. */
export function useFacegate(options: UseFacegateOptions): FacegateHandle {
  const flow = resolveFlow(options);
  const [state, setState] = useState<LivenessState>(IDLE_STATE);
  const [signal, setSignal] = useState<FaceSignal | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const controllerRef = useRef<FaceFlowController | null>(null);
  const sourceRef = useRef<MediaPipeSource | null>(null);
  const containerRef = useRef<HTMLElement | null>(null);
  const flashingRef = useRef(false);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const mountVideo = useCallback((el: HTMLElement | null) => {
    containerRef.current = el;
    const video = sourceRef.current?.video;
    if (el && video && video.parentElement !== el) el.append(video);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const source = new MediaPipeSource(optionsRef.current.camera);
    sourceRef.current = source;
    const facing = optionsRef.current.camera?.facing ?? "user";
    if (facing === "user") source.video.style.transform = "scaleX(-1)";
    Object.assign(source.video.style, { width: "100%", height: "100%", objectFit: "cover" });
    if (containerRef.current) containerRef.current.append(source.video);

    const boot = async () => {
      try {
        await source.initialize();
        if (cancelled) return;
        const o = optionsRef.current;
        const controller: FaceFlowController =
          flow === "enroll"
            ? new FaceEnrollController({
                source,
                capturer: source,
                client: o.client,
                externalId: o.subjectId ?? "",
                name: o.subjectName,
                replace: o.replaceEnrollment,
                config: o.config,
              })
            : new FaceVerifyController({
                source,
                capturer: source,
                client: o.client,
                subjectId: flow === "verify" ? o.subjectId : null,
                purpose: o.purpose,
                config: o.config,
                clientInfo: { platform: "web", ...o.clientInfo },
              });
        controllerRef.current = controller;
        controller.subscribe((s) => {
          setState(s);
          const flashing = s.phase === "flash";
          if (flashing !== flashingRef.current) {
            flashingRef.current = flashing;
            optionsRef.current.onFlashChanged?.(flashing);
          }
          if (s.phase === "success" || s.phase === "failed") {
            source.stopStream();
            if (s.result) optionsRef.current.onResult?.(s.result);
          }
        });
        source.subscribe(setSignal);
        source.startStream();
        setReady(true);
        if (optionsRef.current.autoStart ?? true) await controller.start();
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e : new Error(String(e)));
      }
    };
    void boot();

    return () => {
      cancelled = true;
      controllerRef.current?.dispose();
      controllerRef.current = null;
      source.dispose();
      source.video.remove();
      sourceRef.current = null;
      setReady(false);
      setState(IDLE_STATE);
    };
  }, [options.client, flow, options.subjectId, options.purpose]);

  const start = useCallback(async () => {
    await controllerRef.current?.start();
  }, []);
  const cancel = useCallback(() => controllerRef.current?.cancel(), []);

  return {
    state,
    signal,
    flow,
    ready,
    error,
    controller: controllerRef.current,
    source: sourceRef.current,
    mountVideo,
    start,
    cancel,
  };
}
