import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";
import { GITHUB_URL } from "./site";

function Wordmark() {
  return <span className="text-lg font-semibold tracking-tight text-brand dark:text-teal-300">Lumiface</span>;
}

export function baseOptions(): BaseLayoutProps {
  return {
    nav: { title: <Wordmark />, url: "/" },
    githubUrl: GITHUB_URL,
    links: [
      { text: "Docs", url: "/docs", active: "nested-url" },
      { text: "Policy reference", url: "/docs/policy-reference" },
      { text: "API", url: "/docs/api" },
    ],
  };
}
