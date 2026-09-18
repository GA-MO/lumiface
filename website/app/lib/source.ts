import { loader } from "fumadocs-core/source";
import { defineDocs } from "fumadocs-mdx/macro";

export const DOCS_BASE_URL = "/docs";

export const docs = defineDocs({ dir: "content/docs" });

export const source = loader({ baseUrl: DOCS_BASE_URL, source: docs.toFumadocsSource() });
