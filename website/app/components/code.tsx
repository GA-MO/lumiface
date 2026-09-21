import { createElement, type ReactNode } from "react";
import type { HastNode } from "@/lib/code.server";

function render(node: HastNode, key: number): ReactNode {
  if (node.type === "text") return node.value;
  if (node.type !== "element" || !node.tagName) return null;
  const { className, class: cls, style, ...rest } = node.properties ?? {};
  const props: Record<string, unknown> = { key, ...rest };
  const classes = className ?? cls;
  if (Array.isArray(classes)) props.className = classes.join(" ");
  else if (typeof classes === "string") props.className = classes;
  if (typeof style === "string") {
    props.style = Object.fromEntries(
      style
        .split(";")
        .filter(Boolean)
        .map((d) => {
          const i = d.indexOf(":");
          return [d.slice(0, i).trim(), d.slice(i + 1).trim()];
        }),
    );
  }
  return createElement(node.tagName, props, ...(node.children ?? []).map(render));
}

/** Renders the highlighted tree; the outer `<pre>` is replaced by the caller's own so layout classes apply. */
export function Code({ hast, className }: { hast: HastNode; className?: string }) {
  const pre = hast.children?.find((c) => c.tagName === "pre");
  const code = pre?.children?.find((c) => c.tagName === "code");
  return (
    <pre className={`shiki ${className ?? ""}`}>
      <code>{(code?.children ?? []).map(render)}</code>
    </pre>
  );
}
