import { docsPageGroups, docsPageRaw } from "@/lib/llms";
import { docsPageMarkdown, type DocsPageSummary } from "@/lib/markdown";
import { absoluteUrl, SITE_SUMMARY } from "@/lib/site";

const TEXT_HEADERS = { "Content-Type": "text/plain; charset=utf-8" };

async function pageBlock(summary: DocsPageSummary) {
  return docsPageMarkdown(summary, await docsPageRaw(summary)).trim();
}

export async function loader() {
  const summaries = docsPageGroups().flatMap((g) => g.pages);
  const blocks = await Promise.all(summaries.map(pageBlock));
  const intro = ["# Facegate — full documentation", "", SITE_SUMMARY, "", `Index: ${absoluteUrl("/llms.txt")}.`].join("\n");
  return new Response(`${[intro, ...blocks].join("\n\n---\n\n")}\n`, { headers: TEXT_HEADERS });
}
