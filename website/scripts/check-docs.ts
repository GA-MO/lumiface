// Fails when code names something the docs do not: reason codes, stream events, client-side codes.
// Wired into the ship gate so a new code or event cannot land without its line in the docs.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const docs = readAll(join(root, "website/content/docs"), [".mdx"]);

function readAll(dir: string, exts: string[]): string {
  let out = "";
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out += readAll(p, exts);
    else if (exts.some((e) => name.endsWith(e))) out += readFileSync(p, "utf8") + "\n";
  }
  return out;
}

function codesIn(text: string, pattern: RegExp): Set<string> {
  return new Set([...text.matchAll(pattern)].map((m) => m[1]));
}

const missing: string[] = [];
const IGNORE = new Set(["OK", "GET", "POST", "PUT", "DELETE", "HEAD", "BEARER"]);

const serverSrc = readAll(join(root, "server/app/routers"), [".py"]) + readAll(join(root, "server/app/services"), [".py"]) + readFileSync(join(root, "server/app/deps.py"), "utf8");
for (const code of codesIn(serverSrc, /"([A-Z][A-Z_]{3,})"/g)) {
  if (IGNORE.has(code) || code.startsWith("HTTP_")) continue;
  if (!docs.includes(`\`${code}\``)) missing.push(`reason code ${code} (server/app) not in docs/reason-codes.mdx`);
}

const events = readFileSync(join(root, "server/app/routers/sessions.py"), "utf8").match(/EVENT_NAMES = \(([^)]*)\)/)?.[1] ?? "";
for (const ev of codesIn(events, /"([a-z_]+)"/g)) {
  if (!docs.includes(`"name":"${ev}`) && !docs.includes(`\`${ev}\``)) missing.push(`stream event ${ev} not in docs/api.mdx`);
}

const sdkSrc = readAll(join(root, "packages/lumiface/lib"), [".dart"]) + readAll(join(root, "packages/lumiface-react/src"), [".ts", ".tsx"]);
for (const code of codesIn(sdkSrc, /clientError\(['"]([A-Z_]+)['"]/g)) {
  if (code === "OK") continue;
  if (!docs.includes(`\`${code}\``)) missing.push(`client code ${code} (SDK) not in docs/reason-codes.mdx`);
}

if (missing.length) {
  console.error("docs out of step with code:\n  " + missing.join("\n  "));
  process.exit(1);
}
console.log("docs cover every reason code, stream event and client code");
