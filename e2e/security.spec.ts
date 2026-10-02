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
    if (response?.url().startsWith("https://")) {
      expect(response.headers()["strict-transport-security"]).toBe(
        "max-age=31536000",
      );
    } else {
      expect(response?.headers()["strict-transport-security"]).toBeUndefined();
    }
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

test("API real rejeita CSRF e origens inválidas", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium-390",
    "Prova de segurança compartilhada pela stack",
  );
  await page.goto("/login");
  const origin = new URL(page.url()).origin;
  const loginPayload = {
    email: "admin.e2e@example.com",
    password: "ClientOps E2E admin password 2026!",
  };
  const loginHeaders = { "X-ClientOps-Request": "browser-v1" };
  for (const badOrigin of [undefined, "null", "https://evil.example"]) {
    const response = await page.request.post("/api/v1/auth/login", {
      data: loginPayload,
      headers: badOrigin
        ? { ...loginHeaders, Origin: badOrigin }
        : loginHeaders,
    });
    expect(response.status()).toBe(403);
  }
  const loggedIn = await page.request.post("/api/v1/auth/login", {
    data: loginPayload,
    headers: { ...loginHeaders, Origin: origin },
  });
  expect(loggedIn.status()).toBe(200);
  const session = await page.request.get("/api/v1/auth/session");
  expect(session.status()).toBe(200);
  const csrf = (await session.json()).data.csrf_token as string;
  const mutation = { data: { trade_name: "Rejected" } };
  const missingCsrf = await page.request.patch("/api/v1/business-profile", {
    ...mutation,
    headers: { Origin: origin },
  });
  expect(missingCsrf.status()).toBe(403);
  const badCsrf = await page.request.patch("/api/v1/business-profile", {
    ...mutation,
    headers: { Origin: origin, "X-CSRF-Token": "invalid" },
  });
  expect(badCsrf.status()).toBe(403);
  for (const badOrigin of [undefined, "null", "https://evil.example"]) {
    const response = await page.request.patch("/api/v1/business-profile", {
      ...mutation,
      headers: badOrigin
        ? { Origin: badOrigin, "X-CSRF-Token": csrf }
        : { "X-CSRF-Token": csrf },
    });
    expect(response.status()).toBe(403);
  }
  const validSession = await page.request.get("/api/v1/auth/session");
  expect(validSession.status()).toBe(200);
});
