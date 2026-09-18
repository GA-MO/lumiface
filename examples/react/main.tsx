import { StrictMode, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

import { LumifaceClient, LumifaceView, TH, sessionFromJson, type FaceFlow, type LumifaceScope, type VerifyResult } from "@lumiface/react";

type Mode = "checkin" | "login" | "liveness" | "enroll" | "custom";

/** The browser's side of the example backend (examples/backend, proxied at /api). No key in here. */
const backend = {
  async post<T>(path: string, body: unknown): Promise<T> {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : (j.detail?.reason_code ?? `HTTP_${r.status}`));
    return j as T;
  },
  // The backend forwards Lumiface's JSON as is; sessionFromJson turns it into the SDK's session.
  session: (subjectId: string | null, purpose: string) => backend.post<Record<string, unknown>>("/api/face/session", { subject_id: subjectId, purpose }).then(sessionFromJson),
  enrolToken: (subjectId: string) => backend.post<{ token: string }>("/api/face/enrol-token", { subject_id: subjectId }).then((j) => j.token),
  done: (sessionId: string) => backend.post<{ used: boolean; result: { ok: boolean; reason_code: string; verification_id: number | null } | null }>("/api/face/done", { session_id: sessionId }),
};

function CustomOverlay({ scope }: { scope: LumifaceScope }) {
  const box = scope.displayBox;
  const accent = scope.state.phase === "success" ? "#69f0ae" : scope.state.phase === "failed" ? "#ff5252" : "#ffab40";
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      {box && !scope.isDone && (
        <div style={{ position: "absolute", left: `${box.left * 100}%`, top: `${box.top * 100}%`, width: `${box.width * 100}%`, height: `${box.height * 100}%`, border: `3px solid ${accent}`, borderRadius: 16 }} />
      )}
      <div style={{ position: "absolute", left: 16, right: 16, bottom: 16, background: "rgba(0,0,0,0.8)", borderRadius: 16, padding: 16, textAlign: "center" }}>
        <div style={{ color: accent, fontSize: 20, fontWeight: 700 }}>{scope.message}</div>
        {scope.isDone && <div style={{ opacity: 0.7, marginTop: 6 }}>match {scope.result?.scores.match?.toFixed(3) ?? "-"} · spoof {scope.result?.scores.spoof?.toFixed(3) ?? "-"}</div>}
      </div>
    </div>
  );
}

function App() {
  const [serverUrl, setServerUrl] = useState(localStorage.getItem("fg.url") ?? "http://localhost:8000");
  const [subjectId, setSubjectId] = useState(localStorage.getItem("fg.subject") ?? "");
  const [thai, setThai] = useState(false);
  const [debug, setDebug] = useState(false);
  const [mode, setMode] = useState<Mode | null>(null);
  const [device, setDevice] = useState<VerifyResult | null>(null);
  const [verdict, setVerdict] = useState<string | null>(null);
  const client = useMemo(() => new LumifaceClient({ baseUrl: serverUrl }), [serverUrl]);

  const open = (m: Mode) => {
    localStorage.setItem("fg.url", serverUrl);
    localStorage.setItem("fg.subject", subjectId);
    setDevice(null);
    setVerdict(null);
    setMode(m);
  };

  // What a real app does when the flow ends: tell the backend, let it read the outcome itself.
  const onResult = async (r: VerifyResult) => {
    setDevice(r);
    if (!r.sessionId) return;
    try {
      const s = await backend.done(r.sessionId);
      setVerdict(s.result ? `backend read the session: ok=${s.result.ok} reason=${s.result.reason_code} verification=${s.result.verification_id ?? "-"}` : "backend: no upload recorded for this session");
    } catch (e) {
      setVerdict(`backend error: ${e}`);
    }
  };

  const flow: FaceFlow = mode === "enroll" ? "enroll" : mode === "liveness" ? "liveness" : "verify";
  const common = { client, strings: thai ? TH : undefined, showDebug: debug, onResult, onDone: () => setMode(null) };
  const session = (purpose: string, subject: string | null = subjectId || null) => () => backend.session(subject, purpose);

  return (
    <main>
      <h2>Lumiface React demo</h2>
      {mode === null ? (
        <>
          <label>Lumiface server URL (the browser uploads here with a session token)</label>
          <input value={serverUrl} onChange={(e) => setServerUrl(e.target.value)} />
          <label>Subject id</label>
          <input value={subjectId} onChange={(e) => setSubjectId(e.target.value)} />
          <label><input type="checkbox" checked={thai} onChange={(e) => setThai(e.target.checked)} style={{ width: "auto" }} /> Thai strings</label>
          <label><input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} style={{ width: "auto" }} /> Debug overlay (face box + signals)</label>
          <div>
            <button onClick={() => open("checkin")}>Check-in</button>
            <button onClick={() => open("login")}>Login (themed)</button>
            <button onClick={() => open("liveness")}>Liveness only</button>
            <button onClick={() => open("enroll")} disabled={!subjectId}>Enrol from camera</button>
            <button onClick={() => open("custom")}>Custom overlay</button>
          </div>
          <p style={{ fontSize: 12, opacity: 0.7 }}>
            Sessions and enrol tokens come from <code>/api/face/*</code>: the example backend (<code>examples/backend</code>,
            <code>bun run dev:backend</code>) that holds the project key, the way your own backend would. This page never sees it.
          </p>
          {device && <pre>device: {JSON.stringify(device, null, 2)}</pre>}
          {verdict && <pre>{verdict}</pre>}
        </>
      ) : (
        <div className="stage">
          {mode === "custom" ? (
            <LumifaceView {...common} sessionProvider={session("custom")} renderOverlay={(scope) => <CustomOverlay scope={scope} />} />
          ) : mode === "login" ? (
            <LumifaceView {...common} sessionProvider={session("login")} theme={{ guideShape: "roundedRect", guideActive: "#2dd4bf", guideSuccess: "#2dd4bf" }} />
          ) : mode === "enroll" ? (
            <LumifaceView {...common} flow="enroll" enrolTokenProvider={() => backend.enrolToken(subjectId)} />
          ) : (
            <LumifaceView {...common} flow={flow} sessionProvider={session(mode, flow === "liveness" ? null : subjectId || null)} />
          )}
        </div>
      )}
      {mode !== null && <button onClick={() => setMode(null)}>Close</button>}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
