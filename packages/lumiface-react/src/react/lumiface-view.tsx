import { useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { progressOf, type LivenessState } from "../controller.ts";
import { EN, messageFor, type LivenessStrings } from "../strings.ts";
import type { Box, FaceFlow, FaceSignal, VerifyResult } from "../types.ts";
import { useLumiface, type LumifaceHandle, type UseLumifaceOptions } from "./use-lumiface.ts";

export interface LumifaceTheme {
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

export const DEFAULT_THEME: LumifaceTheme = {
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
export interface LumifaceScope extends LumifaceHandle {
  strings: LivenessStrings;
  theme: LumifaceTheme;
  message: string;
  result: VerifyResult | null;
  isDone: boolean;
  /** `signal.box` flipped for a mirrored preview, for drawing. */
  displayBox: Box | null;
}

export interface LumifaceViewProps extends UseLumifaceOptions {
  strings?: LivenessStrings;
  theme?: Partial<LumifaceTheme>;
  showDebug?: boolean;
  style?: CSSProperties;
  className?: string;
  /** Replaces the whole default overlay; the camera stays underneath. */
  renderOverlay?: (scope: LumifaceScope) => ReactNode;
  renderPrompt?: (scope: LumifaceScope) => ReactNode;
  renderProgress?: (scope: LumifaceScope) => ReactNode;
  renderResult?: (scope: LumifaceScope) => ReactNode;
  /** Must fill the box with `scope.state.flashColor` for the server check to work. */
  renderFlash?: (scope: LumifaceScope) => ReactNode;
  renderLoading?: () => ReactNode;
  renderError?: (error: Error) => ReactNode;
  onDone?: () => void;
  onStateChanged?: (state: LivenessState) => void;
}

/** Maps a full-frame box into the part of the frame that `object-fit: cover` shows in a container of `containerAspect`, mirrored if needed. */
function displayBoxOf(signal: FaceSignal | null, mirrored: boolean, videoAspect: number, containerAspect: number): Box | null {
  const b = signal?.box ?? null;
  if (!b) return null;
  let { left, top, width, height } = b;
  if (videoAspect > 0 && containerAspect > 0 && videoAspect !== containerAspect) {
    if (videoAspect > containerAspect) {
      const visible = containerAspect / videoAspect;
      left = (left - (1 - visible) / 2) / visible;
      width /= visible;
    } else {
      const visible = videoAspect / containerAspect;
      top = (top - (1 - visible) / 2) / visible;
      height /= visible;
    }
  }
  if (mirrored) left = 1 - left - width;
  return { left, top, width, height };
}

function guideColor(theme: LumifaceTheme, phase: LivenessState["phase"]) {
  if (phase === "success") return theme.guideSuccess;
  if (phase === "failed") return theme.guideFailed;
  if (phase === "challenge") return theme.guideActive;
  return theme.guide;
}

/** Dimmed mask with a face-shaped cut-out whose colour follows the phase. */
export function FaceGuide({ theme, phase, box }: { theme: LumifaceTheme; phase: LivenessState["phase"]; box?: Box | null }) {
  const ref = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const maskId = useId();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setSize({ width: el.clientWidth, height: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const { width, height } = size;
  const w = width * theme.guideWidthFraction;
  const h = w * theme.guideAspectRatio;
  const x = (width - w) / 2;
  const y = height * theme.guideCenterY - h / 2;
  const rx = theme.guideShape === "oval" ? w / 2 : w * 0.2;
  const ry = theme.guideShape === "oval" ? h / 2 : w * 0.2;
  const color = guideColor(theme, phase);
  return (
    <svg ref={ref} width={width || undefined} height={height || undefined} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block" }}>
      {theme.guideShape !== "none" && width > 0 && (
        <>
          <defs>
            <mask id={maskId}>
              <rect width={width} height={height} fill="#fff" />
              <rect x={x} y={y} width={w} height={h} rx={rx} ry={ry} fill="#000" />
            </mask>
          </defs>
          <rect width={width} height={height} fill={theme.mask} mask={`url(#${maskId})`} />
          <rect x={x} y={y} width={w} height={h} rx={rx} ry={ry} fill="none" stroke={color} strokeWidth={theme.guideStrokeWidth} />
        </>
      )}
      {box && width > 0 && (
        <rect x={box.left * width} y={box.top * height} width={box.width * width} height={box.height * height} fill="none" stroke="#00e5ff" strokeWidth={2} />
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
  scope: LumifaceScope;
  showDebug: boolean;
  renderPrompt?: LumifaceViewProps["renderPrompt"];
  renderProgress?: LumifaceViewProps["renderProgress"];
  renderResult?: LumifaceViewProps["renderResult"];
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
export function LumifaceView(props: LumifaceViewProps) {
  const { strings = EN, theme: themePatch, showDebug = false, style, className, renderOverlay, renderPrompt, renderProgress, renderResult, renderFlash, renderLoading, renderError, onDone, onStateChanged, ...options } = props;
  const theme = { ...DEFAULT_THEME, ...themePatch };
  const handle = useLumiface(options);
  const rootRef = useRef<HTMLDivElement>(null);
  const [containerAspect, setContainerAspect] = useState(0);
  const lastReported = useRef<LivenessState | null>(null);
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const update = () => setContainerAspect(el.clientHeight > 0 ? el.clientWidth / el.clientHeight : 0);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    if (lastReported.current === handle.state) return;
    lastReported.current = handle.state;
    onStateChanged?.(handle.state);
  }, [handle.state, onStateChanged]);
  const scope: LumifaceScope = {
    ...handle,
    strings,
    theme,
    message: messageFor(strings, handle.state, handle.flow),
    result: handle.state.result,
    isDone: handle.state.phase === "success" || handle.state.phase === "failed",
    displayBox: displayBoxOf(handle.signal, handle.source?.isMirrored ?? true, handle.source?.aspectRatio ?? 0, containerAspect),
  };
  const flashing = handle.state.phase === "flash" && handle.state.flashColor;
  return (
    <div ref={rootRef} className={className} style={{ position: "relative", overflow: "hidden", background: theme.background, width: "100%", height: "100%", ...style }}>
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
