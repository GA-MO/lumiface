# Example backend

The part of *your* system that holds the Lumiface project key and the users' photos. Lumiface
never talks to an anonymous device about who it is and keeps no faces; your application backend
does both, because it has the login and the user records. This ~100-line FastAPI app stands in
for it so the Flutter example and the React demo run the real flow on a laptop: its users are an
in-memory dict (id, name, registration photo) filled from the apps' Users tab. It is not part of
the Lumiface server and needs none of its models.

```bash
cd examples/backend
LUMIFACE_URL=http://localhost:8000 LUMIFACE_KEY=lf_sk_change-me uv run uvicorn main:app --host 0.0.0.0 --port 8010
# or from the repo root: bun run dev:backend
```

| Route | Does | Real backend |
|---|---|---|
| `POST /api/users` multipart `{user_id, name, photo}` | keeps the photo in memory | your registration: the photo is already in your users table |
| `POST /api/face/session` `{user_id?, purpose}` | reads that user's photo, `POST /v1/sessions` with the key and `reference_photo`, returns the JSON for the device; no `user_id` = liveness only | takes the user from its own login, never from the device |
| `POST /api/face/done` `{session_id}` | `GET /v1/sessions/{id}` with the key, joined with its own `session_id → user`, answers `{…status, user_id, verified}` | grants what the session was for when `verified`; ignores what the device says |
| `GET /api/users`, `DELETE /api/users/{id}`, `GET /api/face/verifications`, `GET/PUT /api/face/policy…` | helpers for the example apps' other tabs | |

Copy `/api/face/session` and `/api/face/done` into your backend and replace the `user_id` handling
with your session's user and your own photo store. The device-side code in the examples then
works unchanged.
