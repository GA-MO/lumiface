import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";
import { Logo } from "@/components/logo";
import { GITHUB_URL } from "./site";

export function baseOptions(): BaseLayoutProps {
  return {
    nav: { title: <Logo />, url: "/" },
    githubUrl: GITHUB_URL,
    links: [
      { text: "Docs", url: "/docs", active: "nested-url" },
      { text: "Policy reference", url: "/docs/policy-reference" },
      { text: "API", url: "/docs/api" },
    ],
  };
}
