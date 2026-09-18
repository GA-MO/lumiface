import type { Config } from "@react-router/dev/config";
import { createGetUrl, getSlugs } from "fumadocs-core/source";
import { glob } from "node:fs/promises";

const DOCS_BASE_URL = "/docs";
const DOCS_CONTENT_DIR = "content/docs";
const AGENT_SURFACE_PATHS = ["/api/search", "/llms.txt", "/llms-full.txt", "/sitemap.xml", "/robots.txt", "/404.html"];
const STATIC_BUILD = process.env.VITE_LUMIFACE_STATIC === "1";
const BASENAME = process.env.VITE_LUMIFACE_BASE_PATH ?? "/";

const getDocsUrl = createGetUrl(DOCS_BASE_URL);

async function collectDocsPaths() {
  const paths = new Set<string>([DOCS_BASE_URL]);
  for await (const entry of glob("**/*.mdx", { cwd: DOCS_CONTENT_DIR })) {
    const slugs = getSlugs(entry);
    paths.add(getDocsUrl(slugs));
    if (slugs.length > 0) paths.add(`${getDocsUrl(slugs)}.md`);
  }
  return paths;
}

export default {
  ssr: !STATIC_BUILD,
  basename: BASENAME,
  async prerender({ getStaticPaths }) {
    return [...new Set([...getStaticPaths(), ...AGENT_SURFACE_PATHS, ...(await collectDocsPaths())])];
  },
} satisfies Config;
