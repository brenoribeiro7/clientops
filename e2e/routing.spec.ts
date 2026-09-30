import { expect, test } from "@playwright/test";

for (const path of ["/q/deep", "/admin/deep", "/tech/deep"]) {
  test(`deep link ${path} mantém o fallback correto`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(
      page.getByRole("heading", { name: "Não encontramos este endereço" }),
    ).toBeVisible();
  });
}

test("asset ausente e API ausente não recebem fallback HTML", async ({
  request,
}) => {
  const asset = await request.get("/assets/missing.js");
  expect(asset.status()).toBe(404);
  expect(asset.headers()["content-type"]).toContain("text/html");
  expect(await asset.text()).not.toContain('<div id="root"></div>');

  const api = await request.get("/api/v1/missing");
  expect(api.status()).toBe(404);
  expect(api.headers()["content-type"]).toContain("application/json");
  expect((await api.json()).error.code).toBe("NOT_FOUND");
});
