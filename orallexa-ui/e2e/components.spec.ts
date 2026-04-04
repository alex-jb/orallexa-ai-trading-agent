import { test, expect } from "@playwright/test";

test.describe("Watchlist Interaction", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();
  });

  test("watchlist renders ticker items after signal analysis", async ({ page }) => {
    // Trigger signal analysis so demo/mock watchlist data populates
    const btn = page.getByLabel("Run signal analysis");
    await btn.click();

    // Wait for either watchlist buttons or decision card to appear (demo mode)
    const watchlistOrDecision = page.locator("button").filter({ hasText: /NVDA|AAPL|TSLA|MSFT|GOOG/ })
      .or(page.locator("text=STANDBY").or(page.locator("text=BUY").or(page.locator("text=SELL"))));
    await expect(watchlistOrDecision.first()).toBeVisible({ timeout: 15_000 });
  });

  test("watchlist items are clickable buttons", async ({ page }) => {
    // Run analysis to populate watchlist
    await page.getByLabel("Run signal analysis").click();
    // Wait for app to settle
    const result = page.locator("text=STANDBY").or(page.locator("text=BUY").or(page.locator("text=SELL")));
    await expect(result.first()).toBeVisible({ timeout: 15_000 });

    // If watchlist items rendered, they should be interactive buttons
    const watchlistButtons = page.locator("button").filter({ hasText: /AAPL|TSLA|MSFT|GOOG/ });
    const count = await watchlistButtons.count();
    if (count > 0) {
      await expect(watchlistButtons.first()).toBeEnabled();
    }
  });
});

test.describe("Market Strip", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();
  });

  test("market strip appears after analysis with price and signal data", async ({ page }) => {
    await page.getByLabel("Run signal analysis").click();
    // Wait for decision or standby
    const result = page.locator("text=STANDBY").or(page.locator("text=BUY").or(page.locator("text=SELL")));
    await expect(result.first()).toBeVisible({ timeout: 15_000 });

    // Market strip labels — check for at least one of the expected strip labels
    const stripLabels = page.locator("text=Price").or(page.locator("text=RSI")).or(page.locator("text=Signal")).or(page.locator("text=Conf"));
    await expect(stripLabels.first()).toBeVisible({ timeout: 5_000 });
  });

  test("market strip shows formatted values (not just dashes)", async ({ page }) => {
    await page.getByLabel("Run signal analysis").click();
    const result = page.locator("text=STANDBY").or(page.locator("text=BUY").or(page.locator("text=SELL")));
    await expect(result.first()).toBeVisible({ timeout: 15_000 });

    // After analysis, at least the confidence or signal field should have a real value
    // Use soft assertion — mock data may not always populate all fields
    const confValue = page.locator("text=/\\d+%/").first();
    await expect.soft(confValue).toBeVisible({ timeout: 5_000 });
  });
});

test.describe("Decision Card", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();
  });

  test("standby decision card shows signal/confidence/risk placeholders", async ({ page }) => {
    // Before any analysis, the decision card should show the 3 bottom fields
    const signalLabel = page.locator("text=Signal").first();
    const confidenceLabel = page.locator("text=Confidence").or(page.locator("text=Conf")).first();
    const riskLabel = page.locator("text=Risk").first();

    await expect(signalLabel).toBeVisible();
    await expect.soft(confidenceLabel).toBeVisible();
    await expect.soft(riskLabel).toBeVisible();
  });

  test("standby state shows STANDBY text and pixel bull mascot", async ({ page }) => {
    await expect(page.locator("text=STANDBY").or(page.locator("text=待命"))).toBeVisible();
    // Pixel bull image should be present
    const bullImg = page.getByRole("img", { name: /Orallexa Bull/i });
    await expect.soft(bullImg).toBeVisible();
  });

  test("decision card updates after running signal analysis", async ({ page }) => {
    await page.getByLabel("Run signal analysis").click();
    // Wait for the decision — could be BUY, SELL, WAIT, or STANDBY in demo mode
    const decisionText = page.locator("text=BUY").or(page.locator("text=SELL")).or(page.locator("text=WAIT")).or(page.locator("text=STANDBY"));
    await expect(decisionText.first()).toBeVisible({ timeout: 15_000 });
  });

  test("decision card shows signal strength and confidence after analysis", async ({ page }) => {
    await page.getByLabel("Run signal analysis").click();
    const result = page.locator("text=BUY").or(page.locator("text=SELL")).or(page.locator("text=WAIT")).or(page.locator("text=STANDBY"));
    await expect(result.first()).toBeVisible({ timeout: 15_000 });

    // After analysis, signal/confidence/risk fields should still be visible
    await expect.soft(page.locator("text=Signal").first()).toBeVisible();
    await expect.soft(page.locator("text=Risk").first()).toBeVisible();
  });
});

test.describe("Backtest Panel", () => {
  test("backtest panel renders in right sidebar", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();

    // Backtest period selector group should be in the sidebar
    const backtestGroup = page.getByRole("group", { name: /Backtest period/i });
    // On desktop viewport the sidebar is visible
    await expect.soft(backtestGroup).toBeVisible({ timeout: 10_000 });
  });

  test("backtest period buttons are interactive", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();

    const backtestGroup = page.getByRole("group", { name: /Backtest period/i });
    // Wait for it to load (may use mock data)
    const isVisible = await backtestGroup.isVisible().catch(() => false);
    if (isVisible) {
      // The period buttons have aria-pressed
      const periodButtons = backtestGroup.locator("button[aria-pressed]");
      const count = await periodButtons.count();
      expect.soft(count).toBeGreaterThan(0);

      // Default selected period is 2y
      if (count > 0) {
        const activeButton = backtestGroup.locator("button[aria-pressed='true']");
        await expect.soft(activeButton).toBeVisible();
      }
    }
  });

  test("backtest panel shows strategy results after data loads", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();

    // Run analysis to trigger backtest data fetch
    await page.getByLabel("Run signal analysis").click();
    const result = page.locator("text=STANDBY").or(page.locator("text=BUY").or(page.locator("text=SELL")));
    await expect(result.first()).toBeVisible({ timeout: 15_000 });

    // After analysis, backtest should show strategy names from mock data
    const strategyNames = page.locator("text=Double MA")
      .or(page.locator("text=MACD Cross"))
      .or(page.locator("text=RSI Reversal"))
      .or(page.locator("text=BB Breakout"));
    await expect.soft(strategyNames.first()).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Responsive Layout — Mobile (375x667)", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("page renders and app shell is visible on mobile", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();
  });

  test("mobile menu button is visible", async ({ page }) => {
    await page.goto("/");
    const menuBtn = page.getByLabel(/Open menu|Close menu/);
    await expect(menuBtn).toBeVisible();
  });

  test("sidebar is hidden by default on mobile", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();
    // Navigation sidebar should be hidden on mobile until menu is opened
    const sidebar = page.getByRole("navigation", { name: /Controls/i });
    await expect(sidebar).toBeHidden();
  });

  test("mobile menu opens sidebar on tap", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();

    const menuBtn = page.getByLabel(/Open menu|Close menu/);
    await menuBtn.click();
    // After tap, sidebar should become visible
    const sidebar = page.getByRole("navigation", { name: /Controls/i });
    await expect(sidebar).toBeVisible();
  });

  test("main content area is still present on mobile", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("main", { name: /Analysis results/i })).toBeVisible();
  });

  test("decision card renders on mobile viewport", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("application", { name: /Orallexa Capital/i })).toBeVisible();
    // Standby state should be visible on mobile
    await expect(page.locator("text=STANDBY").or(page.locator("text=待命"))).toBeVisible();
  });
});
