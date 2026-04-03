"use client";

import { useEffect } from "react";

export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js")
        .then((reg) => {
          // Check for updates every 60 minutes
          setInterval(() => reg.update(), 60 * 60 * 1000);
        })
        .catch(() => {});
    }
  }, []);

  return null;
}
