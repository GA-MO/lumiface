/** Who talks to whom in one verification: the app, your backend, Lumiface. Inline SVG, themed through the
 *  docs' CSS variables so it reads in light and dark. Lives on the Concepts page; the backend page refers to its
 *  step numbers (1–6 and 14–18 are the backend's part). */

const LANES = [
  { x: 205, title: "App (browser / phone)", sub: "holds only the session token" },
  { x: 500, title: "Your backend", sub: "holds the key, the users, their photos" },
  { x: 795, title: "Lumiface server", sub: "judges the stream, keeps no face" },
] as const;

type Arrow = { n: number; y: number; from: 0 | 1 | 2; to: 0 | 1 | 2; label: string; note?: string; kind?: "key" | "weak" };
type Note = { n: number; y: number; lane: 0 | 1 | 2; lines: string[]; kind?: "warn" | "key" };

const ARROWS: Arrow[] = [
  { n: 1, y: 122, from: 0, to: 1, label: "POST /api/face/session", note: "your login cookie; no id, no photo" },
  { n: 3, y: 232, from: 1, to: 2, label: "POST /v1/sessions  { reference_photo, purpose }", note: "X-API-Key", kind: "key" },
  { n: 5, y: 344, from: 2, to: 1, label: "201 { session_id, session_token, mode: \"verify\", client_config }" },
  { n: 6, y: 384, from: 1, to: 0, label: "the same JSON, untouched", note: "the token is the app's only credential" },
  { n: 7, y: 446, from: 0, to: 2, label: "WS /v1/sessions/{id}/stream   hello { token, format }" },
  { n: 9, y: 548, from: 2, to: 0, label: "plan { oval, flash_colors, client_config }" },
  { n: 11, y: 654, from: 0, to: 2, label: "video chunks + events (aligned, challenge_done, flash …) → end" },
  { n: 13, y: 764, from: 2, to: 0, label: "result { ok, reason_code }   → onResult()", note: "a copy on the device: a signal, not a decision", kind: "weak" },
  { n: 14, y: 822, from: 0, to: 1, label: "POST /api/face/done { session_id }" },
  { n: 15, y: 870, from: 1, to: 2, label: "GET /v1/sessions/{id}", note: "X-API-Key", kind: "key" },
  { n: 16, y: 918, from: 2, to: 1, label: "{ used, reference, result: { ok, reason_code, scores } }", kind: "key" },
  { n: 18, y: 1030, from: 1, to: 0, label: "200 unlocked  /  403 { reason_code }" },
];

const NOTES: Note[] = [
  { n: 2, y: 176, lane: 1, lines: ["look the user up from the login,", "read their photo from your users table"] },
  { n: 4, y: 290, lane: 2, lines: ["one frontal face → embedding on the session row;", "the photo itself is dropped now", "unusable photo → 422 { reason_code }"], kind: "warn" },
  { n: 8, y: 494, lane: 2, lines: ["used = true (single use)", "embedding deleted from the row — memory only"], kind: "warn" },
  { n: 10, y: 600, lane: 0, lines: ["camera on → guide into the oval →", "three flash colours, recording throughout", "(the SDK does all of this)"] },
  { n: 12, y: 710, lane: 2, lines: ["oval ✓  flash ✓  anti-spoof ✓", "match every key and flash frame ✓  consistency ✓", "audit row { reference: true, scores }"], kind: "key" },
  { n: 17, y: 978, lane: 1, lines: ["the one place that decides:", "result.ok && reference && session was for this user"], kind: "key" },
];

const BANDS: [number, number][] = [[78, 396], [770, 1080]];

export function FlowSwimlane() {
  const laneX = (i: number) => LANES[i]!.x;
  // labels cross the dashed lane lines; a halo in the row's own background keeps them legible
  const halo = (y: number) => ({
    stroke: BANDS.some(([a, b]) => y >= a && y <= b) ? "var(--color-fd-accent)" : "var(--color-fd-card)",
    strokeWidth: 5,
    paintOrder: "stroke" as const,
    strokeLinejoin: "round" as const,
  });
  return (
    <figure className="my-6">
      <div className="overflow-x-auto rounded-lg border border-fd-border bg-fd-card">
        <svg
          viewBox="0 0 1000 1080"
          role="img"
          aria-label="Swimlane of one verification: the app asks your backend for a session, your backend creates it on Lumiface with the user's photo, the app streams the camera to Lumiface with the session token, and your backend reads the verdict with the key and decides."
          style={{ display: "block", width: "100%", minWidth: 720, height: "auto", fontSize: 12.5, color: "var(--color-fd-foreground)" }}
        >
          <defs>
            {(["ink", "key", "weak"] as const).map((k) => (
              <marker key={k} id={`sw-${k}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill={k === "weak" ? "var(--color-fd-muted-foreground)" : "currentColor"} />
              </marker>
            ))}
          </defs>

          {/* phases */}
          <rect x="0" y="78" width="1000" height="318" fill="var(--color-fd-accent)" />
          <rect x="0" y="770" width="1000" height="310" fill="var(--color-fd-accent)" />
          {[
            ["1 · CREATE THE SESSION", 98],
            ["2 · THE STREAM (the SDK)", 416],
            ["3 · READ THE VERDICT, DECIDE", 790],
          ].map(([t, y]) => (
            <text key={t} x="14" y={y} fontSize="11" fontWeight="600" letterSpacing="0.08em" fill="var(--color-fd-muted-foreground)">{t}</text>
          ))}

          {/* lanes */}
          {LANES.map((l) => (
            <g key={l.title}>
              <rect x={l.x - 135} y="10" width="270" height="52" rx="8" fill="var(--color-fd-muted)" />
              <text x={l.x} y="32" textAnchor="middle" fontSize="14" fontWeight="600" fill="currentColor">{l.title}</text>
              <text x={l.x} y="50" textAnchor="middle" fontSize="11.5" fill="var(--color-fd-muted-foreground)">{l.sub}</text>
              <line x1={l.x} y1="62" x2={l.x} y2="1070" stroke="var(--color-fd-border)" strokeWidth="1.5" strokeDasharray="4 4" />
            </g>
          ))}

          {ARROWS.map((a) => {
            const x1 = laneX(a.from);
            const x2 = laneX(a.to) + (a.to > a.from ? -3 : 3);
            const mid = (laneX(a.from) + laneX(a.to)) / 2;
            const stroke = a.kind === "weak" ? "var(--color-fd-muted-foreground)" : "currentColor";
            return (
              <g key={a.n}>
                <circle cx="36" cy={a.y} r="10" fill="var(--color-fd-card)" stroke="var(--color-fd-border)" />
                <text x="36" y={a.y + 4} textAnchor="middle" fontSize="11" fontWeight="500" fontFamily="ui-monospace, monospace" fill="currentColor">{a.n}</text>
                <line x1={x1} y1={a.y} x2={x2} y2={a.y} stroke={stroke} strokeWidth={a.kind === "key" ? 3 : 1.6} strokeDasharray={a.kind === "weak" ? "5 4" : undefined} markerEnd={`url(#sw-${a.kind ?? "ink"})`} />
                <text x={mid} y={a.y - 10} textAnchor="middle" fontSize="11.5" fontFamily="ui-monospace, monospace" fill="currentColor" {...halo(a.y)}>{a.label}</text>
                {a.note && <text x={mid} y={a.y + 16} textAnchor="middle" fontSize="11" fill="var(--color-fd-muted-foreground)" {...halo(a.y)}>{a.note}</text>}
              </g>
            );
          })}

          {NOTES.map((n) => {
            const x = laneX(n.lane);
            const h = 16 + n.lines.length * 16;
            const stroke = n.kind === "warn" ? "#b45309" : n.kind === "key" ? "currentColor" : "var(--color-fd-border)";
            return (
              <g key={n.n}>
                <circle cx="36" cy={n.y} r="10" fill="var(--color-fd-card)" stroke="var(--color-fd-border)" />
                <text x="36" y={n.y + 4} textAnchor="middle" fontSize="11" fontWeight="500" fontFamily="ui-monospace, monospace" fill="currentColor">{n.n}</text>
                <rect x={x - 146} y={n.y - h / 2} width="292" height={h} rx="6" fill="var(--color-fd-card)" stroke={stroke} strokeWidth={n.kind ? 1.4 : 1} />
                {n.lines.map((line, i) => (
                  <text key={i} x={x} y={n.y - h / 2 + 18 + i * 16} textAnchor="middle" fontSize="11.5" fill={n.kind === "warn" && i === 1 ? "#b45309" : "currentColor"}>{line}</text>
                ))}
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption className="mt-2 text-sm text-fd-muted-foreground">
        The two bold arrows carry the project key and exist only between your backend and Lumiface. The dashed arrow (13) is the
        verdict as the device sees it; the decision is step 17, from what your backend read itself in step 16.
      </figcaption>
    </figure>
  );
}
