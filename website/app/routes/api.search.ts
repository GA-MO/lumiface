import { createFromSource } from "fumadocs-core/search/server";
import { source } from "@/lib/source";

const searchServer = createFromSource(source);

export function loader() {
  return searchServer.staticGET();
}
