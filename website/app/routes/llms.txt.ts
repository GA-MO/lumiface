import { docsPageGroups, type DocsPageGroup } from "@/lib/llms";
import type { DocsPageSummary } from "@/lib/markdown";
import { absoluteUrl, SITE_SUMMARY } from "@/lib/site";

const TEXT_HEADERS = { "Content-Type": "text/plain; charset=utf-8" };

function pageLine(page: DocsPageSummary) {
  const link = `- [${page.title}](${absoluteUrl(page.markdownPath)})`;
  return page.description ? `${link}: ${page.description}` : link;
}

function groupBlock(group: DocsPageGroup) {
  return `## ${group.title}\n\n${group.pages.map(pageLine).join("\n")}`;
}

export function loader() {
  const intro = ["# Facegate", "", SITE_SUMMARY, "", `Every page links to its Markdown source; the HTML version drops the \`.md\` suffix. Whole documentation in one file: ${absoluteUrl("/llms-full.txt")}`].join("\n");
  return new Response(`${[intro, ...docsPageGroups().map(groupBlock)].join("\n\n")}\n`, { headers: TEXT_HEADERS });
}
