import { frontmatter } from "fumadocs-core/content/md/frontmatter";
import { absoluteUrl } from "./site";
import type { source } from "./source";

type DocsPage = ReturnType<typeof source.getPages>[number];

export interface DocsPageSummary {
  title: string;
  description: string;
  slugs: string[];
  path: string;
  markdownPath: string;
  file: string;
}

const MDX_ESM_STATEMENT = /^(?:import|export)\s/;
const CODE_FENCE = /^\s*(?:`{3,}|~{3,})/;

/** Turns an MDX body into plain Markdown an agent can read: no ESM lines. */
export function mdxBodyToMarkdown(body: string) {
  const out: string[] = [];
  let inFence = false;
  for (const line of body.split("\n")) {
    if (CODE_FENCE.test(line)) inFence = !inFence;
    if (!inFence && MDX_ESM_STATEMENT.test(line)) continue;
    out.push(line);
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export function docsPageSummary(page: DocsPage): DocsPageSummary {
  return {
    title: page.data.title ?? page.slugs.at(-1) ?? "Docs",
    description: page.data.description ?? "",
    slugs: [...page.slugs],
    path: page.url,
    markdownPath: `${page.url}.md`,
    file: page.path,
  };
}

export function docsPageMarkdown(summary: DocsPageSummary, raw: string) {
  const { content } = frontmatter(raw);
  const description = summary.description ? `${summary.description}\n\n` : "";
  return `# ${summary.title}\n\nSource: ${absoluteUrl(summary.path)}\n\n${description}${mdxBodyToMarkdown(content)}\n`;
}
