import { cp, mkdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE_DIR = fileURLToPath(new URL("..", import.meta.url));
const CLIENT_DIR = path.join(SITE_DIR, "build/client");
const OUT_DIR = path.join(SITE_DIR, "../pages-site");
const basePath = (process.env.VITE_LUMIFACE_BASE_PATH ?? "/").replace(/^\/|\/$/g, "");

/** React Router prerenders under the basename and Vite writes assets at the client root; a static host serves one folder, so both fold into pages-site. */
async function assemble() {
  await rm(OUT_DIR, { recursive: true, force: true });
  await mkdir(OUT_DIR, { recursive: true });
  await cp(basePath ? path.join(CLIENT_DIR, basePath) : CLIENT_DIR, OUT_DIR, { recursive: true });
  if (basePath) await cp(path.join(CLIENT_DIR, "assets"), path.join(OUT_DIR, "assets"), { recursive: true });
  const notFound = path.join(OUT_DIR, "404.html", "index.html");
  const parked = path.join(OUT_DIR, "404.parked.html");
  await rename(notFound, parked);
  await rm(path.join(OUT_DIR, "404.html"), { recursive: true });
  await rename(parked, path.join(OUT_DIR, "404.html"));
}

await assemble();
console.log(`static site assembled in ${OUT_DIR}`);
