"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getNotificationPermission,
  getSwRegistration,
  sendLocalNotification,
} from "../components/ServiceWorkerRegistrar";

interface UseNotificationsReturn {
  permission: NotificationPermission;
  requestPermission: () => Promise<NotificationPermission>;
  notify: (title: string, body: string, tag?: string) => Promise<boolean>;
}

export function useNotifications(): UseNotificationsReturn {
  const [permission, setPermission] = useState<NotificationPermission>("default");

  useEffect(() => {
    // Sync initial permission state once client-side
    if ("Notification" in window) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync of browser permission state on mount
      setPermission(Notification.permission);
    }

    // Poll briefly for SW registration to settle permission state
    const id = setInterval(() => {
      const current = getNotificationPermission();
      setPermission((prev) => (prev !== current ? current : prev));
    }, 1000);

    // Stop polling after 10s
    const timeout = setTimeout(() => clearInterval(id), 10_000);
    return () => {
      clearInterval(id);
      clearTimeout(timeout);
    };
  }, []);

  const requestPermission = useCallback(async (): Promise<NotificationPermission> => {
    if (!("Notification" in window)) return "denied";
    const result = await Notification.requestPermission();
    setPermission(result);
    return result;
  }, []);

  const notify = useCallback(
    async (title: string, body: string, tag?: string): Promise<boolean> => {
      if (permission !== "granted") return false;
      if (!getSwRegistration()) return false;
      return sendLocalNotification(title, body, tag);
    },
    [permission]
  );

  return { permission, requestPermission, notify };
}
