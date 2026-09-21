import { readFileSync } from "node:fs";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// /api/face/* goes to the example backend (examples/backend, `bun run dev:backend`), the stand-in
// for your own application backend that holds the project key. The browser never sees the key.
// /v1 (and its WebSocket) is proxied to the Lumiface server so a phone on the LAN can use this
// origin for both: with DEMO_TLS_CERT/DEMO_TLS_KEY set the page is served over https, which the
// camera needs on anything but localhost; point the page's server URL at https://<mac-ip>:3010.
const tls = process.env.DEMO_TLS_CERT && process.env.DEMO_TLS_KEY
  ? { cert: readFileSync(process.env.DEMO_TLS_CERT), key: readFileSync(process.env.DEMO_TLS_KEY) }
  : undefined;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3010,
    host: tls ? true : undefined,
    https: tls,
    cors: tls ? true : undefined, // the Flutter web example on :3020 uses this origin for /api and /v1 too
    proxy: {
      "/api": process.env.DEMO_BACKEND_URL ?? "http://localhost:8010",
      "/v1": { target: process.env.DEMO_SERVER_URL ?? "http://localhost:8000", ws: true },
    },
  },
});
