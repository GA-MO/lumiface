/** The demo backend (`website/demo-backend`) that mints liveness sessions for the live demo and names the server
 *  the browser streams to. Unset (local dev, previews), the demo runs against a stand-in that judges nothing. */
export const DEMO_URL: string | null = ((import.meta.env.VITE_LUMIFACE_DEMO_URL as string | undefined) ?? "").replace(/\/$/, "") || null;
