/**
 * The example apps' backend, in TypeScript: the part of *your* system that holds the project key
 * and the users' photos. Same routes as `examples/backend` (Python), so the Flutter example and the
 * React demo run against either. It is not part of Lumiface; it needs Bun and nothing else.
 *
 *     cd examples/backend-node
 *     LUMIFACE_URL=http://localhost:8000 LUMIFACE_KEY=lf_sk_change-me bun run dev     # :8010
 *
 * What a real backend does differently: the user comes from the login, not from the request body,
 * and the photo comes from the users table. The shape of the three face routes is what to copy.
 */
const LUMIFACE_URL = (process.env.LUMIFACE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const LUMIFACE_KEY = process.env.LUMIFACE_KEY ?? "lf_sk_change-me";
const PORT = Number(process.env.PORT ?? 8010);

// Your user store: here a Map that lives as long as the process; in a real backend, your users table.
const USERS = new Map<string, { name: string; photo: Uint8Array }>();
// Which user each session was created for. The verdict from Lumiface names no user (it keeps none),
// so this is what `/api/face/done` decides with — never what the browser says.
const SESSIONS = new Map<string, string | null>();

async function lumiface(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-API-Key", LUMIFACE_KEY);
  return fetch(`${LUMIFACE_URL}${path}`, { ...init, headers });
}

/** Forward Lumiface's answer as is, status and reason_code included. */
async function forward(r: Response): Promise<Response> {
  const body = await r.text();
  return new Response(body, { status: r.status, headers: { "Content-Type": r.headers.get("Content-Type") ?? "application/json" } });
}

const json = (data: unknown, status = 200) => Response.json(data, { status });
const error = (status: number, reason_code: string) => json({ detail: { reason_code } }, status);

async function handle(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const { method } = req;
  const path = url.pathname;

  // --- Registration: the photo lands here, in your store, never on Lumiface.
  if (path === "/api/users" && method === "GET") {
    return json([...USERS].map(([id, u]) => ({ id, name: u.name })));
  }
  if (path === "/api/users" && method === "POST") {
    const form = await req.formData();
    const id = String(form.get("user_id") ?? "");
    const photo = form.get("photo");
    if (!id || !(photo instanceof Blob)) return error(422, "USER_ID_AND_PHOTO_REQUIRED");
    USERS.set(id, { name: String(form.get("name") ?? ""), photo: new Uint8Array(await photo.arrayBuffer()) });
    return json({ id, name: USERS.get(id)!.name }, 201);
  }
  const user = path.match(/^\/api\/users\/([^/]+)$/);
  if (user && method === "DELETE") {
    USERS.delete(decodeURIComponent(user[1]!));
    return new Response(null, { status: 204 });
  }

  // --- The session: who is verified is fixed here, from your own photo of the user.
  if (path === "/api/face/session" && method === "POST") {
    const body = (await req.json()) as { user_id?: string | null; purpose?: string };
    let reference_photo: string | null = null;
    if (body.user_id) {
      const u = USERS.get(body.user_id);
      if (!u) return error(404, "USER_NOT_FOUND");
      reference_photo = Buffer.from(u.photo).toString("base64");
    }
    const r = await lumiface("/v1/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reference_photo, purpose: body.purpose ?? "demo" }),
    });
    if (!r.ok) return forward(r);
    const session = (await r.json()) as { session_id: string };
    SESSIONS.set(session.session_id, body.user_id ?? null);
    return json(session); // straight to the browser: it holds only the session token
  }

  // --- The verdict: read from Lumiface with the key, decided against your own record of the session.
  if (path === "/api/face/done" && method === "POST") {
    const { session_id } = (await req.json()) as { session_id: string };
    const r = await lumiface(`/v1/sessions/${encodeURIComponent(session_id)}`);
    if (!r.ok) return forward(r);
    const status = (await r.json()) as { reference: boolean; result: { ok: boolean } | null };
    const user_id = SESSIONS.get(session_id) ?? null;
    const verified = Boolean(status.result?.ok) && status.reference && user_id !== null;
    // A real backend now grants what the session was for (signs in `user_id`, unlocks the feature).
    return json({ ...status, user_id, verified });
  }

  // --- Helpers for the example apps' other tabs.
  if (path === "/api/face/verifications" && method === "GET") {
    return forward(await lumiface(`/v1/verifications${url.search}`));
  }
  if (path === "/api/face/policy" && (method === "GET" || method === "PUT")) {
    return forward(await lumiface("/v1/policy", { method, headers: { "Content-Type": "application/json" }, body: method === "PUT" ? await req.text() : undefined }));
  }
  if (path === "/api/face/policy/presets" && method === "GET") {
    return forward(await lumiface("/v1/policy/presets"));
  }
  if (path === "/health") {
    const up = await lumiface("/health").then((r) => r.ok, () => false);
    return json({ ok: true, lumiface: LUMIFACE_URL, lumiface_up: up });
  }
  return error(404, "NOT_FOUND");
}

Bun.serve({
  port: PORT,
  fetch: (req) =>
    handle(req).then((res) => {
      res.headers.set("Access-Control-Allow-Origin", "*");
      res.headers.set("Access-Control-Allow-Headers", "*");
      res.headers.set("Access-Control-Allow-Methods", "*");
      return res;
    }),
});
console.log(`example backend (bun) on http://localhost:${PORT} → ${LUMIFACE_URL}`);
