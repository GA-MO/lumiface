import { index, route, type RouteConfig } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("docs/:group?/:section?/:page.md", "routes/docs.md.ts"),
  route("docs/*", "routes/docs.tsx"),
  route("api/search", "routes/api.search.ts"),
  route("llms.txt", "routes/llms.txt.ts"),
  route("llms-full.txt", "routes/llms-full.txt.ts"),
  route("sitemap.xml", "routes/sitemap.xml.ts"),
  route("robots.txt", "routes/robots.txt.ts"),
  route("404.html", "routes/not-found.tsx"),
] satisfies RouteConfig;
