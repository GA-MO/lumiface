import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// /api/face/* goes to the example backend (examples/backend, `bun run dev:backend`), the stand-in
// for your own application backend that holds the project key. The browser never sees the key.
export default defineConfig({
  plugins: [react()],
  server: { port: 3010, proxy: { "/api": process.env.DEMO_BACKEND_URL ?? "http://localhost:8010" } },
});
