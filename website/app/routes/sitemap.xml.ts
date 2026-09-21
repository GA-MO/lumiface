import { docsPageGroups } from "@/lib/llms";
import { absoluteUrl } from "@/lib/site";
import { DOCS_BASE_URL } from "@/lib/source";

const XML_HEADERS = { "Content-Type": "application/xml; charset=utf-8" };

export function loader() {
  const paths = [...new Set(["/", DOCS_BASE_URL, ...docsPageGroups().flatMap((g) => g.pages.map((p) => p.path))])];
  const entries = paths.map((p) => `  <url>\n    <loc>${absoluteUrl(p)}</loc>\n  </url>`).join("\n");
  return new Response(`<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries}\n</urlset>\n`, { headers: XML_HEADERS });
}
