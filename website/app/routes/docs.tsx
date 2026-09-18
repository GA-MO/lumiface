import { useFumadocsLoader } from "fumadocs-core/source/client";
import { DocsLayout } from "fumadocs-ui/layouts/docs";
import { DocsBody, DocsDescription, DocsPage, DocsTitle, EditOnGitHub, MarkdownCopyButton } from "fumadocs-ui/layouts/docs/page";
import { data } from "react-router";
import { useMDXComponents } from "@/components/mdx";
import { baseOptions } from "@/lib/layout.shared";
import { DOCS_CONTENT_GITHUB_URL } from "@/lib/site";
import { DOCS_BASE_URL, docs, source } from "@/lib/source";
import type { Route } from "./+types/docs";

function toSlugs(splat: string | undefined) {
  return (splat ?? "").split("/").filter((s) => s.length > 0);
}

export async function loader({ params }: Route.LoaderArgs) {
  const slugs = toSlugs(params["*"]);
  const page = source.getPage(slugs);
  if (!page) throw new Response("Not found", { status: 404 });
  const pageTree = await source.serializePageTree(source.getPageTree());
  return data({ path: page.path, slug: slugs.join("/"), pageTree });
}

function ContentPage({ path, slug }: { path: string; slug: string }) {
  const page = docs.getPage(path);
  if (!page) throw new Error(`Unknown docs page: ${path}`);
  const Mdx = page.body;
  const markdownPath = slug ? `${DOCS_BASE_URL}/${slug}.md` : undefined;
  return (
    <DocsPage toc={page.toc} tableOfContent={{ style: "clerk" }} breadcrumb={{ includeRoot: { url: DOCS_BASE_URL }, includePage: true }}>
      <title>{`${page.title} | Lumiface`}</title>
      <meta name="description" content={page.description} />
      {markdownPath && <link rel="alternate" type="text/markdown" href={markdownPath} />}
      <DocsTitle>{page.title}</DocsTitle>
      <DocsDescription>{page.description}</DocsDescription>
      <div className="flex flex-wrap items-center gap-2">
        {markdownPath && <MarkdownCopyButton markdownUrl={markdownPath}>Copy for AI</MarkdownCopyButton>}
        <EditOnGitHub href={`${DOCS_CONTENT_GITHUB_URL}/${path}`} />
      </div>
      <DocsBody>
        <Mdx components={useMDXComponents()} />
      </DocsBody>
    </DocsPage>
  );
}

export default function DocsRoute({ loaderData }: Route.ComponentProps) {
  const { path, slug, pageTree } = useFumadocsLoader(loaderData);
  return (
    <DocsLayout {...baseOptions()} tree={pageTree}>
      <ContentPage path={path} slug={slug} />
    </DocsLayout>
  );
}
