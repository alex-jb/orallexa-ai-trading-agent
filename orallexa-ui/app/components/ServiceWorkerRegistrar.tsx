"use client";

import { useEffect, useRef } from "react";

let swRegistration: ServiceWorkerRegistration | null = null;
let notificationPermission: NotificationPermission = "default";

/** Send a local notification via the active service worker. */
export async function sendLocalNotification(
  title: string,
  body: string,
  tag?: string
): Promise<boolean> {
  if (notificationPermission !== "granted" || !swRegistration) return false;
  try {
    await swRegistration.showNotification(title, {
      body,
      icon: "/logo.svg",
      badge: "/icon-192.png",
      tag: tag || "orallexa-signal",
      data: { url: "/" },
    } as NotificationOptions & { renotify?: boolean });
    return true;
  } catch {
    return false;
  }
}

/** Returns current permission state. */
export function getNotificationPermission(): NotificationPermission {
  return notificationPermission;
}

/** Returns the active SW registration (or null). */
export function getSwRegistration(): ServiceWorkerRegistration | null {
  return swRegistration;
}

export function ServiceWorkerRegistrar() {
  const registered = useRef(false);

  useEffect(() => {
    if (registered.current) return;
    registered.current = true;

    if (!("serviceWorker" in navigator)) return;

    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => {
        swRegistration = reg;

        // Check for updates every 60 minutes
        setInterval(() => reg.update(), 60 * 60 * 1000);

        // Request notification permission after SW is ready
        if ("Notification" in window && Notification.permission === "default") {
          Notification.requestPermission().then((perm) => {
            notificationPermission = perm;
          });
        } else if ("Notification" in window) {
          notificationPermission = Notification.permission;
        }
      })
      .catch(() => {});
  }, []);

  return null;
}
