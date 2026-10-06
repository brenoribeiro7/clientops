import { expect, test } from "@playwright/test";

const pages = [
  ["/admin", "Entrar no ClientOps"],
  ["/tech/today", "Entrar no ClientOps"],
  ["/q", "Orçamento indisponível"],
  ["/login", "Entrar no ClientOps"],
] as const;

for (const [path, heading] of pages) {
  test(`${path} apresenta o shell esperado sem overflow`, async ({ page }) => {
    await page.goto(path);
    await expect(
      page.getByRole("heading", { level: 1, name: heading }),
    ).toBeVisible();
    const sizes = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(sizes.scrollWidth).toBeLessThanOrEqual(sizes.clientWidth);
  });
}

test("Drawer administrativo restaura foco", async ({ page }, testInfo) => {
  test.skip(
    (testInfo.project.use.viewport?.width ?? 0) >= 1024,
    "A navegação desktop substitui o Drawer.",
  );
  await page.goto("/login");
  await page.getByLabel("E-mail").fill("admin.e2e@example.com");
  await page.getByLabel("Senha").fill("ClientOps E2E admin password 2026!");
  const response = page.waitForResponse(
    (candidate) =>
      candidate.url().includes("/api/v1/auth/login") &&
      candidate.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Entrar" }).click();
  await response;
  await expect(
    page.getByRole("heading", { name: "Visão administrativa" }),
  ).toBeVisible();
  const trigger = page.getByRole("button", {
    name: "Abrir menu administrativo",
  });
  await trigger.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(trigger).toBeFocused();
});
