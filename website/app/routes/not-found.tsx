import { HomeLayout } from "fumadocs-ui/layouts/home";
import { Link } from "react-router";
import { baseOptions } from "@/lib/layout.shared";

export function meta() {
  return [{ title: "Not found | Facegate" }];
}

export default function NotFoundRoute() {
  return (
    <HomeLayout {...baseOptions()}>
      <main className="mx-auto w-full max-w-3xl px-4 py-16">
        <h1 className="text-2xl font-semibold">Page not found</h1>
        <p className="mt-2 text-muted-foreground">
          Start from the <Link to="/docs">docs</Link> or the <Link to="/">home page</Link>.
        </p>
      </main>
    </HomeLayout>
  );
}
