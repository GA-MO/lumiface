# Example backend

The part of *your* system that holds the Lumiface project key. Lumiface never talks to an
anonymous device about who it is; your application backend does, because it has the login. This
~100-line FastAPI app stands in for it so the Flutter example and the React demo run the real
flow on a laptop. It is not part of the Lumiface server and needs none of its models.

```bash
cd examples/backend
LUMIFACE_URL=http://localhost:8000 LUMIFACE_KEY=lf_sk_change-me uv run uvicorn main:app --host 0.0.0.0 --port 8010
# or from the repo root: bun run dev:backend
```

| Route | Does | Real backend |
|---|---|---|
| `POST /api/face/session` `{subject_id, purpose}` | `POST /v1/sessions` with the key, returns the JSON for the device | takes `subject_id` from its own login, never from the device |
| `POST /api/face/enrol-token` `{subject_id, name}` | `POST /v1/subjects/tokens` | only for a user it has authenticated |
| `POST /api/face/done` `{session_id}` | `GET /v1/sessions/{id}` — the verdict | acts on `result.ok`, ignores what the device says |
| `GET/POST/DELETE /api/face/subjects…`, `GET /api/face/verifications`, `GET/PUT /api/face/policy…` | admin helpers for the example apps' other tabs | |

Copy the first three routes into your backend and replace the `subject_id` handling with your
session's user. The device-side code in the examples then works unchanged.
