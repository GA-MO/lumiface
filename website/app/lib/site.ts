const PLACEHOLDER_SITE_URL = "https://ga-mo.github.io/lumiface";

function resolveSiteUrl() {
  const configured = process.env.LUMIFACE_SITE_URL?.trim();
  return (configured && configured.length > 0 ? configured : PLACEHOLDER_SITE_URL).replace(/\/+$/, "");
}

/** Origin used by llms.txt, llms-full.txt and sitemap.xml. Set `LUMIFACE_SITE_URL` in the Pages workflow. */
export const SITE_URL = resolveSiteUrl();

export function absoluteUrl(path: string) {
  return `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export const GITHUB_URL = "https://github.com/GA-MO/lumiface";
export const DOCS_CONTENT_GITHUB_URL = `${GITHUB_URL}/blob/main/website/content/docs`;

export const SITE_SUMMARY = [
  "Lumiface is a self-hosted face verification service with active liveness: a FastAPI server (InsightFace ArcFace matching, MiniFASNet and CVPR-2024 anti-spoof, screen-flash reflection check) plus a Flutter package and a React SDK that run the camera side (the oval and the screen flash, with a face box from BlazeFace or Apple Vision) on iOS, Android and the web.",
  "Every project has its own API key and a policy: a preset (balanced, strict, relaxed, emulator) plus overrides for every threshold, changed through the API without redeploying. The session carries the client tunables, so apps follow the policy without a rebuild.",
].join("\n\n");
