# Example backend (TypeScript / Bun)

The same stand-in for *your* backend as [`examples/backend`](../backend) (Python), for teams whose
backend is Node: it holds the Lumiface project key and the users' photos, creates sessions with the
photo as the reference, and reads the verdict. Same routes, so the Flutter example and the React
demo run against either one. No framework, no dependencies beyond Bun.

```bash
cd examples/backend-node
LUMIFACE_URL=http://localhost:8000 LUMIFACE_KEY=lf_sk_change-me bun run dev     # http://localhost:8010
# or from the repo root: bun run dev:backend:node
```

| Route | Does | Real backend |
|---|---|---|
| `POST /api/users` multipart `{user_id, name, photo}` | keeps the photo in memory | your registration: the photo is already in your users table |
| `POST /api/face/session` `{user_id?, purpose}` | reads that user's photo, `POST /v1/sessions` with the key and `reference_photo`, remembers `session_id → user`, returns the JSON for the browser; no `user_id` = liveness only | takes the user from its own login, never from the device |
| `POST /api/face/done` `{session_id}` | `GET /v1/sessions/{id}` with the key, joins it with its own `session_id → user`, answers `{…status, user_id, verified}` | grants what the session was for when `verified` |
| `GET /api/users`, `DELETE /api/users/{id}`, `GET /api/face/verifications`, `GET/PUT /api/face/policy…` | helpers for the example apps' other tabs | |

The three face routes are the whole integration: copy `handle()`'s session and done branches, replace
`USERS` with your users table and `SESSIONS` with a column on your side, and the device-side code in
the examples works unchanged.
