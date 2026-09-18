import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

import { progressOf, type LivenessState } from "../controller.ts";
import { EN, messageFor, type LivenessStrings } from "../strings.ts";
import type { Box, FaceFlow, FaceSignal, VerifyResult } from "../types.ts";
import { useFacegate, type FacegateHandle, type UseFacegateOptions } from "./use-facegate.ts";

export interface FacegateTheme {
  background: string;
  mask: string;
  guide: string;
  guideActive: string;
  guideSuccess: string;
  guideFailed: string;
  guideShape: "oval" | "roundedRect" | "none";
  guideWidthFraction: number;
  guideAspectRatio: number;
  guideCenterY: number;
  guideStrokeWidth: number;
  progress: string;
  progressBackground: string;
  message: CSSProperties;
  showProgress: boolean;
  showButtons: boolean;
}

export const DEFAULT_THEME: FacegateTheme = {
  background: "#000",
  mask: "rgba(0,0,0,0.55)",
  guide: "#fff",
  guideActive: "#ffc107",
  guideSuccess: "#4caf50",
  guideFailed: "#f44336",
  guideShape: "oval",
  guideWidthFraction: 0.72,
  guideAspectRatio: 1.35,
  guideCenterY: 0.42,
  guideStrokeWidth: 4,
  progress: "#fff",
  progressBackground: "rgba(255,255,255,0.25)",
  message: { color: "#fff", fontSize: 22, fontWeight: 600, textAlign: "center", padding: "32px 24px" },
  showProgress: true,
  showButtons: true,
};

/** Everything a render prop needs to draw one moment of a flow. */
export interface FacegateScope extends FacegateHandle {
  strings: LivenessStrings;
  theme: FacegateTheme;
  message: string;
  result: VerifyResult | null;
  isDone: boolean;
  /** `signal.box` flipped for a mirrored preview, for drawing. */
  displayBox: Box | null;
}

export interface FacegateViewProps extends UseFacegateOptions {
  strings?: LivenessStrings;
  theme?: Partial<FacegateTheme>;
  showDebug?: boolean;
  style?: CSSProperties;
  className?: string;
  /** Replaces the whole default overlay; the camera stays underneath. */
  renderOverlay?: (scope: FacegateScope) => ReactNode;
  renderPrompt?: (scope: FacegateScope) => ReactNode;
  renderProgress?: (scope: FacegateScope) => ReactNode;
  renderResult?: (scope: FacegateScope) => ReactNode;
  /** Must fill the box with `scope.state.flashColor` for the server check to work. */
  renderFlash?: (scope: FacegateScope) => ReactNode;
  renderLoading?: () => ReactNode;
  renderError?: (error: Error) => ReactNode;
  onDone?: () => void;
  onStateChanged?: (state: LivenessState) => void;
}

function displayBoxOf(signal: FaceSignal | null, mirrored: boolean): Box | null {
  const b = signal?.box ?? null;
  if (!b || !mirrored) return b;
  return { ...b, left: 1 - b.left - b.width };
}

function guideColor(theme: FacegateTheme, phase: LivenessState["phase"]) {
  if (phase === "success") return theme.guideSuccess;
  if (phase === "failed") return theme.guideFailed;
  if (phase === "challenge") return theme.guideActive;
  return theme.guide;
}

/** Dimmed mask with a face-shaped cut-out whose colour follows the phase. */
export function FaceGuide({ theme, phase, box }: { theme: FacegateTheme; phase: LivenessState["phase"]; box?: Box | null }) {
  const w = theme.guideWidthFraction * 100;
  const h = w * theme.guideAspectRatio;
  const color = guideColor(theme, phase);
  const rx = theme.guideShape === "oval" ? "50%" : "20%";
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
      {theme.guideShape !== "none" && (
        <>
          <defs>
            <mask id="facegate-guide-mask">
              <rect width="100" height="100" fill="#fff" />
              <rect x={50 - w / 2} y={theme.guideCenterY * 100 - h / 2} width={w} height={h} rx={rx} fill="#000" />
            </mask>
          </defs>
          <rect width="100" height="100" fill={theme.mask} mask="url(#facegate-guide-mask)" />
          <rect
            x={50 - w / 2}
            y={theme.guideCenterY * 100 - h / 2}
            width={w}
            height={h}
            rx={rx}
            fill="none"
            stroke={color}
            strokeWidth={theme.guideStrokeWidth / 4}
            vectorEffect="non-scaling-stroke"
          />
        </>
      )}
      {box && (
        <rect x={box.left * 100} y={box.top * 100} width={box.width * 100} height={box.height * 100} fill="none" stroke="#00e5ff" strokeWidth={0.5} vectorEffect="non-scaling-stroke" />
      )}
    </svg>
  );
}

function fmt(v: number | null | undefined) {
  return v === null || v === undefined ? "-" : v.toFixed(2);
}

/** One line of raw detector values, for calibration sessions. */
export function FaceDebugBar({ signal }: { signal: FaceSignal }) {
  const eye = signal.eyeOpenLeft !== null && signal.eyeOpenRight !== null ? (signal.eyeOpenLeft + signal.eyeOpenRight) / 2 : null;
  const px =
    signal.nose && signal.leftEye && signal.rightEye
      ? (signal.nose.x - (signal.leftEye.x + signal.rightEye.x) / 2) / Math.abs(signal.rightEye.x - signal.leftEye.x)
      : null;
  return (
    <div style={{ background: "rgba(0,0,0,0.6)", color: "#fff", fontFamily: "monospace", fontSize: 11, padding: 8 }}>
      faces={signal.faceCount} w={fmt(signal.box?.width)} eye={fmt(eye)} smile={fmt(signal.smile)} yaw={fmt(signal.yaw)} pitch={fmt(signal.pitch)} px={fmt(px)}
    </div>
  );
}

function DefaultOverlay({ scope, showDebug, renderPrompt, renderProgress, renderResult, onDone }: {
  scope: FacegateScope;
  showDebug: boolean;
  renderPrompt?: FacegateViewProps["renderPrompt"];
  renderProgress?: FacegateViewProps["renderProgress"];
  renderResult?: FacegateViewProps["renderResult"];
  onDone?: () => void;
}) {
  const { state, theme, strings } = scope;
  const progress = progressOf(state);
  return (
    <>
      <FaceGuide theme={theme} phase={state.phase} box={showDebug ? scope.displayBox : null} />
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "16px 32px 0" }}>
          {renderProgress
            ? renderProgress(scope)
            : theme.showProgress && state.challengeCount > 0 && (
                <div style={{ height: 4, background: theme.progressBackground, borderRadius: 2 }}>
                  <div style={{ height: "100%", width: `${(progress ?? 0) * 100}%`, background: theme.progress, borderRadius: 2, transition: "width 200ms" }} />
                </div>
              )}
        </div>
        <div style={{ flex: 1 }} />
        {renderPrompt ? renderPrompt(scope) : <div style={theme.message}>{scope.message}</div>}
        {scope.isDone &&
          (renderResult
            ? renderResult(scope)
            : theme.showButtons && (
                <div style={{ textAlign: "center", paddingBottom: 24 }}>
                  <button type="button" onClick={onDone} style={{ padding: "10px 24px", borderRadius: 20, border: 0, fontSize: 16 }}>
                    {state.phase === "success" ? strings.done : strings.retry}
                  </button>
                </div>
              ))}
        {showDebug && scope.signal && <FaceDebugBar signal={scope.signal} />}
      </div>
    </>
  );
}

/**
 * Camera preview plus a flow with a default overlay whose every part can be
 * replaced: `theme` and `strings` for looks and texts, `renderPrompt`,
 * `renderProgress`, `renderResult`, `renderFlash` for single parts, or
 * `renderOverlay` for the whole thing. Fills its parent; give it a size.
 */
export function FacegateView(props: FacegateViewProps) {
  const { strings = EN, theme: themePatch, showDebug = false, style, className, renderOverlay, renderPrompt, renderProgress, renderResult, renderFlash, renderLoading, renderError, onDone, onStateChanged, ...options } = props;
  const theme = { ...DEFAULT_THEME, ...themePatch };
  const handle = useFacegate(options);
  const lastReported = useRef<LivenessState | null>(null);
  useEffect(() => {
    if (lastReported.current === handle.state) return;
    lastReported.current = handle.state;
    onStateChanged?.(handle.state);
  }, [handle.state, onStateChanged]);
  const scope: FacegateScope = {
    ...handle,
    strings,
    theme,
    message: messageFor(strings, handle.state, handle.flow),
    result: handle.state.result,
    isDone: handle.state.phase === "success" || handle.state.phase === "failed",
    displayBox: displayBoxOf(handle.signal, handle.source?.isMirrored ?? true),
  };
  const flashing = handle.state.phase === "flash" && handle.state.flashColor;
  return (
    <div className={className} style={{ position: "relative", overflow: "hidden", background: theme.background, width: "100%", height: "100%", ...style }}>
      <div ref={handle.mountVideo} style={{ position: "absolute", inset: 0 }} />
      {handle.error ? (
        renderError ? renderError(handle.error) : <div style={theme.message}>{strings.cameraError}<br />{handle.error.message}</div>
      ) : !handle.ready ? (
        renderLoading ? renderLoading() : <div style={{ ...theme.message, position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>{strings.starting}</div>
      ) : renderOverlay ? (
        renderOverlay(scope)
      ) : (
        <DefaultOverlay scope={scope} showDebug={showDebug} renderPrompt={renderPrompt} renderProgress={renderProgress} renderResult={renderResult} onDone={onDone} />
      )}
      {flashing && (renderFlash ? renderFlash(scope) : <div style={{ position: "absolute", inset: 0, background: `#${handle.state.flashColor}` }} />)}
    </div>
  );
}

export type { FaceFlow };
