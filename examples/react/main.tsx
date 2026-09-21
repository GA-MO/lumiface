import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

import { LumifaceClient, LumifaceView, TH, sessionFromJson, type FaceFlow, type LumifaceScope, type VerifyResult } from "@lumiface/react";

type Mode = "checkin" | "login" | "liveness" | "custom";
type User = { id: string; name: string };

/** The browser's side of the example backend (examples/backend, proxied at /api). No key in here. */
const backend = {
  async post<T>(path: string, body: unknown): Promise<T> {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : (j.detail?.reason_code ?? `HTTP_${r.status}`));
    return j as T;
  },
  // The backend forwards Lumiface's JSON as is; sessionFromJson turns it into the SDK's session.
  // It picks the reference photo from its own user store; a null user is a liveness session.
  session: (userId: string | null, purpose: string) => backend.post<Record<string, unknown>>("/api/face/session", { user_id: userId, purpose }).then(sessionFromJson),
  done: (sessionId: string) => backend.post<{ used: boolean; reference: boolean; result: { ok: boolean; reason_code: string; verification_id: number | null } | null }>("/api/face/done", { session_id: sessionId }),
  users: () => fetch("/api/users").then((r) => r.json() as Promise<User[]>),
  // Registration: the photo goes to the example backend's own store, never to Lumiface.
  register: async (id: string, name: string, photo: File) => {
    const form = new FormData();
    form.set("user_id", id);
    form.set("name", name);
    form.set("photo", photo);
    const r = await fetch("/api/users", { method: "POST", body: form });
    if (!r.ok) throw new Error(`HTTP_${r.status}`);
  },
  remove: (id: string) => fetch(`/api/users/${encodeURIComponent(id)}`, { method: "DELETE" }),
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
  const [userId, setUserId] = useState(localStorage.getItem("fg.user") ?? "");
  const [users, setUsers] = useState<User[]>([]);
  const [photo, setPhoto] = useState<File | null>(null);
  const refreshUsers = () => backend.users().then(setUsers).catch(() => setUsers([]));
  useEffect(() => {
    refreshUsers();
  }, []);
  const [thai, setThai] = useState(false);
  const [debug, setDebug] = useState(false);
  const [mode, setMode] = useState<Mode | null>(null);
  const [device, setDevice] = useState<VerifyResult | null>(null);
  const [verdict, setVerdict] = useState<string | null>(null);
  const client = useMemo(() => new LumifaceClient({ baseUrl: serverUrl }), [serverUrl]);

  const open = (m: Mode) => {
    localStorage.setItem("fg.url", serverUrl);
    localStorage.setItem("fg.user", userId);
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

  const flow: FaceFlow = mode === "liveness" ? "liveness" : "verify";
  const common = {
    client,
    strings: thai ? TH : undefined,
    showDebug: debug,
    onResult,
    onDone: () => setMode(null),
    camera: { modelUrl: "/models/face_detection_short/model.json" },
  };
  const session = (purpose: string, user: string | null = userId || null) => () => backend.session(user, purpose);
  const register = async () => {
    if (!userId || !photo) return;
    try {
      await backend.register(userId, userId, photo);
      setPhoto(null);
      await refreshUsers();
    } catch (e) {
      setVerdict(`register failed: ${e}`);
    }
  };

  return (
    <main>
      <h2>Lumiface React demo</h2>
      {mode === null ? (
        <>
          <label>Lumiface server URL (the browser uploads here with a session token)</label>
          <input value={serverUrl} onChange={(e) => setServerUrl(e.target.value)} />
          <label>User id (a user of the example backend; its photo is the reference)</label>
          <input value={userId} onChange={(e) => setUserId(e.target.value)} list="users" />
          <datalist id="users">{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</datalist>
          <div>
            <input type="file" accept="image/*" capture="user" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} style={{ width: "auto" }} />
            <button onClick={register} disabled={!userId || !photo}>Register photo for this user</button>
            {users.some((u) => u.id === userId) && <button onClick={() => backend.remove(userId).then(refreshUsers)}>Remove</button>}
          </div>
          <label><input type="checkbox" checked={thai} onChange={(e) => setThai(e.target.checked)} style={{ width: "auto" }} /> Thai strings</label>
          <label><input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} style={{ width: "auto" }} /> Debug overlay (face box + signals)</label>
          <div>
            <button onClick={() => open("checkin")}>Check-in</button>
            <button onClick={() => open("login")}>Login (themed)</button>
            <button onClick={() => open("liveness")}>Liveness only</button>
            <button onClick={() => open("custom")}>Custom overlay</button>
          </div>
          <p style={{ fontSize: 12, opacity: 0.7 }}>
            Sessions come from <code>/api/face/session</code>: the example backend (<code>examples/backend</code>,
            <code>bun run dev:backend</code>) holds the project key and the users' photos, the way your own backend would, and
            sends the photo to Lumiface as the session's reference. This page never sees the key; Lumiface keeps no face.
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
          ) : (
            <LumifaceView {...common} flow={flow} sessionProvider={session(mode, flow === "liveness" ? null : userId || null)} />
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
