import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import { fumadocsMdx } from "fumadocs-mdx/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ command }) => ({
  base: process.env.VITE_LUMIFACE_BASE_PATH ?? "/",
  define: { "process.env.LUMIFACE_SITE_URL": JSON.stringify(process.env.LUMIFACE_SITE_URL ?? "") },
  plugins: [fumadocsMdx(), tailwindcss(), reactRouter()],
  ssr: { noExternal: command === "build" ? true : [] },
  resolve: { alias: [{ find: /^@\//, replacement: `${path.join(root, "app")}/` }] },
}));
