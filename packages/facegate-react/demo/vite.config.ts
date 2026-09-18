import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({ root: "demo", plugins: [react()], server: { port: 3010 } });
