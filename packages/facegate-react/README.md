# @facegate/react

Face verification with active liveness for React 18/19: MediaPipe FaceLandmarker in the browser, the Facegate server behind it.

```tsx
import { FacegateClient, FacegateView } from "@facegate/react";

const client = new FacegateClient({ baseUrl: "https://faces.example.com", apiKey: key });

<div style={{ height: "70vh" }}>
  <FacegateView client={client} subjectId="E001" purpose="login" onResult={(r) => console.log(r)} />
</div>
```

- `FacegateView`: preview + flow + default overlay; `theme`, `strings`, `renderPrompt`, `renderProgress`, `renderResult`, `renderFlash`, `renderOverlay`.
- `useFacegate`: camera and controller lifecycle without markup.
- `FaceVerifyController`, `FaceEnrollController`, `MediaPipeSource`, `FacegateClient`, `EN` / `TH` strings; `@facegate/react/core` has no browser code.

```bash
bun install && bun run dev      # demo on http://localhost:3010
bun run test && bun run typecheck
```

Docs: `website/content/docs/react`.
