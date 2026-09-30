import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const strictCsp = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "style-src-elem 'self'",
  "style-src-attr 'none'",
  "img-src 'self' blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
].join("; ");

for (const path of ["/q", "/login", "/admin/deep", "/tech/deep"]) {
  test(`${path} recebe SEC-05 no documento servido`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.headers()["content-security-policy"]).toBe(strictCsp);
    expect(response?.headers()["referrer-policy"]).toBe("no-referrer");
    expect(response?.headers()["x-content-type-options"]).toBe("nosniff");
    expect(response?.headers()["x-frame-options"]).toBe("DENY");
    expect(response?.headers()["cache-control"]).toBe("no-store");
    expect(await page.locator("[style]").count()).toBe(0);

    await page.evaluate(() => {
      Reflect.set(window, "__clientopsInlineProbe", 0);
      const script = document.createElement("script");
      script.textContent = "window.__clientopsInlineProbe = 1";
      document.body.append(script);
    });
    await page.waitForTimeout(50);
    expect(
      await page.evaluate(() => Reflect.get(window, "__clientopsInlineProbe")),
    ).toBe(0);
  });
}

test("shells não possuem violações axe sérias ou críticas", async ({
  page,
}) => {
  for (const path of ["/admin", "/tech/today", "/q", "/login"]) {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).analyze();
    const blocking = results.violations.filter(
      (violation) =>
        violation.impact === "serious" || violation.impact === "critical",
    );
    expect(blocking, `${path}: ${JSON.stringify(blocking)}`).toEqual([]);
  }
});

test("readiness não é exposta pelo proxy", async ({ request }) => {
  const response = await request.get("/api/v1/health/ready");
  expect(response.status()).toBe(404);
  expect(await response.text()).not.toContain("migration");
  expect(await response.text()).not.toContain("storage");
});
