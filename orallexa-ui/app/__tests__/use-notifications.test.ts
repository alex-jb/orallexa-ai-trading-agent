import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useNotifications } from "../hooks/use-notifications";

// Mock the ServiceWorkerRegistrar module
vi.mock("../components/ServiceWorkerRegistrar", () => ({
  getNotificationPermission: vi.fn(() => "default"),
  getSwRegistration: vi.fn(() => null),
  sendLocalNotification: vi.fn(() => Promise.resolve(true)),
}));

import {
  getNotificationPermission,
  getSwRegistration,
  sendLocalNotification,
} from "../components/ServiceWorkerRegistrar";

const mockGetPermission = vi.mocked(getNotificationPermission);
const mockGetSwReg = vi.mocked(getSwRegistration);
const mockSendNotification = vi.mocked(sendLocalNotification);

describe("useNotifications", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetPermission.mockReturnValue("default");
    mockGetSwReg.mockReturnValue(null);
    mockSendNotification.mockResolvedValue(true);

    // Mock Notification API
    Object.defineProperty(globalThis, "Notification", {
      value: {
        permission: "default",
        requestPermission: vi.fn(() => Promise.resolve("granted")),
      },
      writable: true,
      configurable: true,
    });
  });

  it("returns initial permission state", () => {
    const { result } = renderHook(() => useNotifications());
    expect(result.current.permission).toBe("default");
  });

  it("provides requestPermission function", () => {
    const { result } = renderHook(() => useNotifications());
    expect(typeof result.current.requestPermission).toBe("function");
  });

  it("provides notify function", () => {
    const { result } = renderHook(() => useNotifications());
    expect(typeof result.current.notify).toBe("function");
  });

  it("requestPermission updates state", async () => {
    const { result } = renderHook(() => useNotifications());
    await act(async () => {
      const perm = await result.current.requestPermission();
      expect(perm).toBe("granted");
    });
    expect(result.current.permission).toBe("granted");
  });

  it("notify returns false when permission is not granted", async () => {
    const { result } = renderHook(() => useNotifications());
    // permission is "default", not "granted"
    let sent: boolean = false;
    await act(async () => {
      sent = await result.current.notify("Test", "Body");
    });
    expect(sent).toBe(false);
    expect(mockSendNotification).not.toHaveBeenCalled();
  });

  it("notify returns false when no SW registration", async () => {
    mockGetSwReg.mockReturnValue(null);
    const { result } = renderHook(() => useNotifications());
    // Grant permission first
    await act(async () => {
      await result.current.requestPermission();
    });
    let sent: boolean = false;
    await act(async () => {
      sent = await result.current.notify("Test", "Body");
    });
    expect(sent).toBe(false);
  });

  it("notify calls sendLocalNotification when granted + SW ready", async () => {
    mockGetSwReg.mockReturnValue({} as ServiceWorkerRegistration);
    const { result } = renderHook(() => useNotifications());
    // Grant permission
    await act(async () => {
      await result.current.requestPermission();
    });
    let sent: boolean = false;
    await act(async () => {
      sent = await result.current.notify("Signal", "BUY NVDA", "signal-tag");
    });
    expect(sent).toBe(true);
    expect(mockSendNotification).toHaveBeenCalledWith("Signal", "BUY NVDA", "signal-tag");
  });

  it("handles missing Notification API gracefully", async () => {
    // Remove Notification from window
    const original = globalThis.Notification;
    delete (globalThis as Record<string, unknown>).Notification;
    const { result } = renderHook(() => useNotifications());
    await act(async () => {
      const perm = await result.current.requestPermission();
      expect(perm).toBe("denied");
    });
    // Restore
    Object.defineProperty(globalThis, "Notification", {
      value: original,
      writable: true,
      configurable: true,
    });
  });
});
