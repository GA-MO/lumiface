# @lumiface/react

Face verification with active liveness for React 18/19: MediaPipe FaceLandmarker in the browser, the Lumiface server behind it.

```tsx
import { LumifaceClient, LumifaceView } from "@lumiface/react";

const client = new LumifaceClient({ baseUrl: "https://faces.example.com", apiKey: key });

<div style={{ height: "70vh" }}>
  <LumifaceView client={client} subjectId="E001" purpose="login" onResult={(r) => console.log(r)} />
</div>
```

- `LumifaceView`: preview + flow + default overlay; `theme`, `strings`, `renderPrompt`, `renderProgress`, `renderResult`, `renderFlash`, `renderOverlay`.
- `useLumiface`: camera and controller lifecycle without markup.
- `FaceVerifyController`, `FaceEnrollController`, `MediaPipeSource`, `LumifaceClient`, `EN` / `TH` strings; `@lumiface/react/core` has no browser code.

```bash
bun install && bun run dev      # demo on http://localhost:3010
bun run test && bun run typecheck
```

Docs: `website/content/docs/react`.
