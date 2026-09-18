import type { Node as PageTreeNode } from "fumadocs-core/page-tree";
import { docsPageSummary, type DocsPageSummary } from "./markdown";
import { source } from "./source";

export interface DocsPageGroup {
  title: string;
  pages: DocsPageSummary[];
}

const GROUP_TITLES: Record<string, string> = {
  docs: "Start",
  flutter: "Flutter",
  react: "React",
  server: "Server",
};

function pageOrderFromTree() {
  const order = new Map<string, number>();
  const remember = (url: string) => {
    if (!order.has(url)) order.set(url, order.size);
  };
  const walk = (nodes: PageTreeNode[]) => {
    for (const node of nodes) {
      if (node.type === "page") remember(node.url);
      if (node.type !== "folder") continue;
      if (node.index) remember(node.index.url);
      walk(node.children);
    }
  };
  walk(source.getPageTree().children);
  return order;
}

export function docsPageGroups(): DocsPageGroup[] {
  const order = pageOrderFromTree();
  const pages = [...source.getPages()].sort(
    (a, b) => (order.get(a.url) ?? Number.MAX_SAFE_INTEGER) - (order.get(b.url) ?? Number.MAX_SAFE_INTEGER),
  );
  const groups = new Map<string, DocsPageGroup>();
  for (const page of pages) {
    const summary = docsPageSummary(page);
    const slug = summary.slugs.length > 1 ? summary.slugs[0] : "docs";
    const group = groups.get(slug) ?? { title: GROUP_TITLES[slug] ?? slug, pages: [] };
    group.pages.push(summary);
    groups.set(slug, group);
  }
  return [...groups.values()];
}

export async function docsPageRaw(summary: DocsPageSummary) {
  const page = source.getPage(summary.slugs);
  if (!page) throw new Response(`Unknown docs page: ${summary.path}`, { status: 404 });
  return page.data.getText("raw");
}
