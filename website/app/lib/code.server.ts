import { highlightHast } from "fumadocs-core/highlight";

export interface HastNode {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
  value?: string;
}

/** Shiki as the docs use it: light and dark colours as CSS variables, `.dark` picks one. */
export async function highlightCode(code: string, lang: string): Promise<HastNode> {
  return (await highlightHast(code, { lang })) as unknown as HastNode;
}

/** A single dark theme for blocks that sit on a dark surface in both modes. */
export async function highlightDark(code: string, lang: string): Promise<HastNode> {
  return (await highlightHast(code, { lang, theme: "github-dark" })) as unknown as HastNode;
}
