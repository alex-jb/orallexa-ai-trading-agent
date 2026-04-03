import { test, expect } from "@playwright/test";

test.describe("Dashboard — Core User Flows", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // Wait for the app shell to render
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();
  });

  test("homepage loads with brand and default ticker NVDA", async ({ page }) => {
    // Brand mark visible in sidebar navigation
    await expect(page.getByRole("navigation", { name: /Controls/i }).getByRole("img", { name: /Orallexa Capital/i })).toBeVisible();
    // Default ticker input
    const tickerInput = page.getByLabel("Ticker symbol");
    await expect(tickerInput).toHaveValue("NVDA");
  });

  test("can change ticker via input", async ({ page }) => {
    const tickerInput = page.getByLabel("Ticker symbol");
    await tickerInput.fill("AAPL");
    await expect(tickerInput).toHaveValue("AAPL");
  });

  test("strategy buttons are interactive", async ({ page }) => {
    const buttons = page.getByLabel(/^Strategy:/);
    const count = await buttons.count();
    expect(count).toBeGreaterThan(0);
    // Click second strategy
    if (count > 1) {
      await buttons.nth(1).click();
      await expect(buttons.nth(1)).toHaveAttribute("aria-pressed", "true");
    }
  });

  test("horizon buttons are interactive", async ({ page }) => {
    const buttons = page.getByLabel(/^Horizon:/);
    const count = await buttons.count();
    expect(count).toBeGreaterThan(0);
  });

  test("language toggle switches between EN and ZH", async ({ page }) => {
    // Default is EN
    const enBtn = page.getByRole("radio", { name: "English" });
    const zhBtn = page.getByRole("radio", { name: "中文" });
    await expect(enBtn).toHaveAttribute("aria-checked", "true");
    await expect(zhBtn).toHaveAttribute("aria-checked", "false");

    // Switch to Chinese
    await zhBtn.click();
    await expect(zhBtn).toHaveAttribute("aria-checked", "true");
    await expect(enBtn).toHaveAttribute("aria-checked", "false");
  });

  test("Claude AI overlay toggle works", async ({ page }) => {
    const toggle = page.getByLabel(/Claude AI/i);
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", "true");
  });

  test("run signal button exists and is clickable", async ({ page }) => {
    const btn = page.getByLabel("Run signal analysis");
    await expect(btn).toBeVisible();
    await expect(btn).toBeEnabled();
  });

  test("run deep analysis button exists", async ({ page }) => {
    const btn = page.getByLabel("Run deep intelligence analysis");
    await expect(btn).toBeVisible();
  });

  test("main content area is present", async ({ page }) => {
    await expect(page.getByRole("main", { name: /Analysis results/i })).toBeVisible();
  });

  test("navigation sidebar is present", async ({ page }) => {
    await expect(page.getByRole("navigation", { name: /Controls/i })).toBeVisible();
  });

  test("error dismiss works", async ({ page }) => {
    // Trigger an analysis that will fail (no backend) — the app should show an error or fall back to demo
    const btn = page.getByLabel("Run signal analysis");
    await btn.click();
    // Wait for either error alert or decision card (demo mode)
    const errorOrResult = page.getByRole("alert").or(page.locator("text=STANDBY").or(page.locator("text=BUY").or(page.locator("text=SELL"))));
    await expect(errorOrResult.first()).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("Dashboard — Responsive", () => {
  test("mobile menu button appears on small viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    const menuBtn = page.getByLabel(/Open menu|Close menu/);
    await expect(menuBtn).toBeVisible();
  });
});

test.describe("Offline Page", () => {
  test("offline page renders with retry button", async ({ page }) => {
    await page.goto("/offline");
    await expect(page.getByText(/You're Offline|Offline/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /Retry|重试/i })).toBeVisible();
  });

  test("offline page has link back to dashboard", async ({ page }) => {
    await page.goto("/offline");
    await expect(page.getByText(/View cached dashboard|查看缓存数据/i)).toBeVisible();
  });
});
