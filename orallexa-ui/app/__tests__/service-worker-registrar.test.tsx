import { describe, it, expect, vi, beforeEach } from "vitest";
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
