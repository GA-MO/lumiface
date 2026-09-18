import { docsPageMarkdown, docsPageSummary } from "@/lib/markdown";
import { source } from "@/lib/source";
import type { Route } from "./+types/docs.md";

const MARKDOWN_HEADERS = { "Content-Type": "text/markdown; charset=utf-8" };

export async function loader({ params }: Route.LoaderArgs) {
  const slugs = [params.group, params.section, params.page].filter((s): s is string => typeof s === "string" && s.length > 0);
  const page = source.getPage(slugs);
  if (!page) throw new Response("Not found", { status: 404 });
  const markdown = docsPageMarkdown(docsPageSummary(page), await page.data.getText("raw"));
  return new Response(markdown, { headers: MARKDOWN_HEADERS });
}
