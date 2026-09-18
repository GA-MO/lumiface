# @lumiface/react

Face verification with active liveness for React 18/19: MediaPipe FaceLandmarker in the browser, the Lumiface server behind it.

```tsx
import { LumifaceClient, LumifaceView, sessionFromJson } from "@lumiface/react";

const client = new LumifaceClient({ baseUrl: "https://faces.example.com" }); // apiKey: only in development

<div style={{ height: "70vh" }}>
  <LumifaceView
    client={client}
    subjectId="E001"
    purpose="login"
    sessionProvider={async () => sessionFromJson(await fetch("/api/face/session", { method: "POST" }).then((r) => r.json()))}
    onResult={(r) => console.log(r)}
  />
</div>
```

- `LumifaceView`: preview + flow + default overlay; `theme`, `strings`, `renderPrompt`, `renderProgress`, `renderResult`, `renderFlash`, `renderOverlay`.
- `useLumiface`: camera and controller lifecycle without markup.
- `FaceVerifyController`, `FaceEnrollController`, `MediaPipeSource`, `LumifaceClient`, `EN` / `TH` strings; `@lumiface/react/core` has no browser code.
- The browser never holds the project key: `sessionProvider` fetches the session from your backend and the upload uses its token; `enrolToken` (from `POST /v1/subjects/tokens`) does the same for enrolment.

```bash
bun install && bun run dev      # demo on http://localhost:3010
bun run test && bun run typecheck
```

Docs: `website/content/docs/react`.
