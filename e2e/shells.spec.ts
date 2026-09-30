import { expect, test } from "@playwright/test";

const pages = [
  ["/admin", "Fundação administrativa"],
  ["/tech/today", "Fundação do trabalho técnico"],
  ["/q", "Fundação da experiência pública"],
  ["/login", "Acesso ao ClientOps"],
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
  await page.goto("/admin");
  const trigger = page.getByRole("button", {
    name: "Abrir menu administrativo",
  });
  await trigger.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(trigger).toBeFocused();
});
