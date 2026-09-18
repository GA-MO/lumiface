# @lumiface/react

Face verification with active liveness for React 18/19: MediaPipe FaceLandmarker in the browser, the Lumiface server behind it.

```tsx
import { LumifaceClient, LumifaceView, sessionFromJson } from "@lumiface/react";

const client = new LumifaceClient({ baseUrl: "https://faces.example.com" }); // holds no secret

<div style={{ height: "70vh" }}>
  <LumifaceView
    client={client}
    sessionProvider={async () => sessionFromJson(await fetch("/api/face/session", { method: "POST" }).then((r) => r.json()))}
    onResult={(r) => console.log(r)}
  />
</div>
```

- `LumifaceView`: preview + flow + default overlay; `theme`, `strings`, `renderPrompt`, `renderProgress`, `renderResult`, `renderFlash`, `renderOverlay`.
- `useLumiface`: camera and controller lifecycle without markup.
- `FaceVerifyController`, `FaceEnrollController`, `MediaPipeSource`, `LumifaceClient`, `EN` / `TH` strings; `@lumiface/react/core` has no browser code.
- The browser never holds the project key: `LumifaceClient` cannot take one. `sessionProvider` / `enrolTokenProvider` fetch what your backend minted with two REST calls (`POST /v1/sessions`, `GET /v1/sessions/{id}`); `examples/backend` in the repository is a complete one.

```bash
bun run test && bun run typecheck   # from this package
bun run dev:react                   # from the repo root: examples/react on http://localhost:3010
```

Docs: `website/content/docs/react`.
