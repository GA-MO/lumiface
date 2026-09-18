import { StrictMode, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

import { LumifaceClient, LumifaceView, TH, type FaceFlow, type LumifaceScope, type VerifyResult } from "../src/index.ts";

type Mode = "checkin" | "login" | "liveness" | "enroll" | "custom";

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
  const [baseUrl, setBaseUrl] = useState(localStorage.getItem("fg.url") ?? "http://localhost:8000");
  const [apiKey, setApiKey] = useState(localStorage.getItem("fg.key") ?? "change-me");
  const [subjectId, setSubjectId] = useState(localStorage.getItem("fg.subject") ?? "");
  const [thai, setThai] = useState(false);
  const [mode, setMode] = useState<Mode | null>(null);
  const [last, setLast] = useState<VerifyResult | null>(null);
  const client = useMemo(() => new LumifaceClient({ baseUrl, apiKey }), [baseUrl, apiKey]);

  const open = (m: Mode) => {
    localStorage.setItem("fg.url", baseUrl);
    localStorage.setItem("fg.key", apiKey);
    localStorage.setItem("fg.subject", subjectId);
    setLast(null);
    setMode(m);
  };

  const flow: FaceFlow | undefined = mode === "enroll" ? "enroll" : mode === "liveness" ? "liveness" : mode ? "verify" : undefined;
  const common = { client, strings: thai ? TH : undefined, showDebug: true, onResult: setLast, onDone: () => setMode(null) };

  return (
    <main>
      <h2>Lumiface React demo</h2>
      {mode === null ? (
        <>
          <label>Server URL</label>
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          <label>Project API key</label>
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
          <label>Subject id</label>
          <input value={subjectId} onChange={(e) => setSubjectId(e.target.value)} />
          <label><input type="checkbox" checked={thai} onChange={(e) => setThai(e.target.checked)} style={{ width: "auto" }} /> Thai strings</label>
          <div>
            <button onClick={() => open("checkin")}>Check-in</button>
            <button onClick={() => open("login")}>Login (themed)</button>
            <button onClick={() => open("liveness")}>Liveness only</button>
            <button onClick={() => open("enroll")}>Enrol from camera</button>
            <button onClick={() => open("custom")}>Custom overlay</button>
          </div>
          {last && <pre>{JSON.stringify(last, null, 2)}</pre>}
        </>
      ) : (
        <div className="stage">
          {mode === "custom" ? (
            <LumifaceView {...common} subjectId={subjectId || null} purpose="custom" renderOverlay={(scope) => <CustomOverlay scope={scope} />} />
          ) : mode === "login" ? (
            <LumifaceView {...common} subjectId={subjectId} purpose="login" theme={{ guideShape: "roundedRect", guideActive: "#2dd4bf", guideSuccess: "#2dd4bf" }} />
          ) : (
            <LumifaceView {...common} flow={flow} subjectId={subjectId || null} purpose={mode} replaceEnrollment />
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
