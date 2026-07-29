"use client";

import { useEffect } from "react";

export default function RegionRedirect() {
  useEffect(() => {
    window.location.replace("/?view=opportunities&dimension=region");
  }, []);
  return <main className="redirect-state">正在进入国家/地区机会页…</main>;
}
