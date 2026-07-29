import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Cloudflare Pages runs `npm run build:cloudflare` and needs a static export.
  // The Sites/vinext build produces its own worker bundle and must not enter
  // vinext's Windows-only static-export prerender shutdown path.
  output: process.env.VINEXT_SITES_BUILD === "1" ? undefined : "export",
};

export default nextConfig;
