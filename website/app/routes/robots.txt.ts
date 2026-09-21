import { absoluteUrl } from "@/lib/site";

export function loader() {
  const body = ["User-agent: *", "Allow: /", "", `Sitemap: ${absoluteUrl("/sitemap.xml")}`, `# Documentation for LLM agents: ${absoluteUrl("/llms.txt")} and ${absoluteUrl("/llms-full.txt")}`, ""].join("\n");
  return new Response(body, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
