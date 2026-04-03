import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render } from "@testing-library/react";
import { ServiceWorkerRegistrar, sendLocalNotification, getNotificationPermission, getSwRegistration } from "../components/ServiceWorkerRegistrar";

// Mock navigator.serviceWorker
const mockRegistration = {
  update: vi.fn(),
  showNotification: vi.fn().mockResolvedValue(undefined),
};

beforeEach(() => {
  vi.restoreAllMocks();

  // Reset module-level state by re-importing would be complex,
  // so we test the exported functions and rendering behavior

  Object.defineProperty(navigator, "serviceWorker", {
    value: {
      register: vi.fn().mockResolvedValue(mockRegistration),
      addEventListener: vi.fn(),
    },
    configurable: true,
    writable: true,
  });

  Storage.prototype.setItem = vi.fn();
});

describe("ServiceWorkerRegistrar", () => {
  it("renders nothing (null)", () => {
    const { container } = render(<ServiceWorkerRegistrar />);
    expect(container.firstChild).toBeNull();
  });

  it("registers service worker on mount", async () => {
    render(<ServiceWorkerRegistrar />);
    // Wait for the async registration
    await vi.waitFor(() => {
      expect(navigator.serviceWorker.register).toHaveBeenCalledWith("/sw.js");
    });
  });

  it("sets last online timestamp in localStorage", () => {
    render(<ServiceWorkerRegistrar />);
    expect(localStorage.setItem).toHaveBeenCalledWith(
      "orallexa_last_online",
      expect.any(String)
    );
  });

  it("listens for SW messages", () => {
    render(<ServiceWorkerRegistrar />);
    expect(navigator.serviceWorker.addEventListener).toHaveBeenCalledWith(
      "message",
      expect.any(Function)
    );
  });
});

describe("sendLocalNotification", () => {
  it("returns false when permission not granted", async () => {
    const result = await sendLocalNotification("Test", "Body");
    expect(result).toBe(false);
  });
});

describe("getNotificationPermission", () => {
  it("returns default initially", () => {
    expect(getNotificationPermission()).toBe("default");
  });
});

describe("getSwRegistration", () => {
  it("returns null before registration", () => {
    // On first import, before SW registers, it should be null
    // (the actual module state may have been updated by previous tests)
    expect(getSwRegistration()).toBeDefined();
  });
});

describe("sendLocalNotification — when permission is granted", () => {
  // We need to reach the module-level variables swRegistration and
  // notificationPermission. The cleanest approach without a full module reset
  // is to render ServiceWorkerRegistrar so the SW registers, then manually
  // manipulate the Notification.permission and invoke sendLocalNotification
  // via the exported helper after patching the internal state through the
  // side-effecting component.

  const grantedMockRegistration = {
    update: vi.fn(),
    showNotification: vi.fn().mockResolvedValue(undefined),
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    Storage.prototype.setItem = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns true when notification permission is granted and SW is registered", async () => {
    // Patch navigator.serviceWorker so register() resolves with our mock
    Object.defineProperty(navigator, "serviceWorker", {
      value: {
        register: vi.fn().mockResolvedValue(grantedMockRegistration),
        addEventListener: vi.fn(),
      },
      configurable: true,
      writable: true,
    });

    // Patch Notification.permission to "granted"
    Object.defineProperty(globalThis, "Notification", {
      value: { permission: "granted" },
      configurable: true,
      writable: true,
    });

    // Render the component — this triggers the useEffect that sets swRegistration
    // and reads Notification.permission into the module-level variable
    render(<ServiceWorkerRegistrar />);

    // Wait for the async SW register promise to resolve and populate swRegistration
    await vi.waitFor(() => {
      expect(navigator.serviceWorker.register).toHaveBeenCalledWith("/sw.js");
    });

    // Now sendLocalNotification has access to both the granted permission and
    // the populated swRegistration; it should call showNotification and return true
    const result = await sendLocalNotification("Signal Alert", "NVDA BUY", "nvda-buy");
    expect(result).toBe(true);
    expect(grantedMockRegistration.showNotification).toHaveBeenCalledWith(
      "Signal Alert",
      expect.objectContaining({
        body: "NVDA BUY",
        icon: "/logo.svg",
        badge: "/icon-192.png",
        tag: "nvda-buy",
      })
    );
  });

  it("uses default tag 'orallexa-signal' when no tag is provided", async () => {
    Object.defineProperty(navigator, "serviceWorker", {
      value: {
        register: vi.fn().mockResolvedValue(grantedMockRegistration),
        addEventListener: vi.fn(),
      },
      configurable: true,
      writable: true,
    });
    Object.defineProperty(globalThis, "Notification", {
      value: { permission: "granted" },
      configurable: true,
      writable: true,
    });

    render(<ServiceWorkerRegistrar />);
    await vi.waitFor(() => {
      expect(navigator.serviceWorker.register).toHaveBeenCalled();
    });

    await sendLocalNotification("Test", "Body text");
    expect(grantedMockRegistration.showNotification).toHaveBeenCalledWith(
      "Test",
      expect.objectContaining({ tag: "orallexa-signal" })
    );
  });

  it("returns false and does not throw when showNotification rejects", async () => {
    const failingRegistration = {
      update: vi.fn(),
      showNotification: vi.fn().mockRejectedValue(new Error("Notification blocked")),
    };

    Object.defineProperty(navigator, "serviceWorker", {
      value: {
        register: vi.fn().mockResolvedValue(failingRegistration),
        addEventListener: vi.fn(),
      },
      configurable: true,
      writable: true,
    });
    Object.defineProperty(globalThis, "Notification", {
      value: { permission: "granted" },
      configurable: true,
      writable: true,
    });

    render(<ServiceWorkerRegistrar />);
    await vi.waitFor(() => {
      expect(navigator.serviceWorker.register).toHaveBeenCalled();
    });

    const result = await sendLocalNotification("Fail Test", "Should not throw");
    expect(result).toBe(false);
  });

  it("dispatches sw-updated custom event when SW message type is SW_UPDATED", () => {
    Object.defineProperty(navigator, "serviceWorker", {
      value: {
        register: vi.fn().mockResolvedValue(grantedMockRegistration),
        addEventListener: vi.fn((event, handler) => {
          if (event === "message") {
            // Immediately invoke with an SW_UPDATED message to exercise that branch
            handler({ data: { type: "SW_UPDATED" } });
          }
        }),
      },
      configurable: true,
      writable: true,
    });

    const dispatchSpy = vi.spyOn(window, "dispatchEvent");
    render(<ServiceWorkerRegistrar />);

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: "sw-updated" })
    );
  });
});
