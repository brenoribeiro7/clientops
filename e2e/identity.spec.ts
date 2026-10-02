import { expect, test } from "@playwright/test";

test.use({ screenshot: "off", trace: "off" });

const adminEmail = "admin.e2e@example.com";
const adminPassword = "ClientOps E2E admin password 2026!";

async function login(
  page: import("@playwright/test").Page,
  email: string,
  password: string,
) {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
}

test("árvore pública /q não consulta sessão privada", async ({ page }) => {
  const sessionRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/auth/session"))
      sessionRequests.push(request.url());
  });
  await page.goto("/q");
  await expect(
    page.getByRole("heading", { name: "Fundação da experiência pública" }),
  ).toBeVisible();
  expect(sessionRequests).toEqual([]);
});

test("fluxo real Admin e Técnico com cookie, CSRF e senha temporária", async ({
  page,
}, testInfo) => {
  const technicianEmail = `tech.${testInfo.project.name.replaceAll("-", ".")}@example.com`;
  await login(page, adminEmail, adminPassword);
  await expect(
    page.getByRole("heading", { name: "Visão administrativa" }),
  ).toBeVisible();
  const sessionCookie = (await page.context().cookies()).find((cookie) =>
    cookie.name.includes("clientops_session"),
  );
  expect(sessionCookie?.httpOnly).toBe(true);
  expect(sessionCookie?.sameSite).toBe("Lax");
  if (page.url().startsWith("https://")) {
    expect(sessionCookie?.name).toBe("__Host-clientops_session");
    expect(sessionCookie?.secure).toBe(true);
  } else {
    expect(sessionCookie?.name).toBe("clientops_session_dev");
  }

  const csrfFailure = await page.evaluate(async () => {
    const response = await fetch("/api/v1/business-profile", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trade_name: "Rejected" }),
    });
    return { status: response.status, body: await response.json() };
  });
  expect(csrfFailure.status).toBe(403);
  expect(csrfFailure.body.error.code).toBe("CSRF_FAILED");

  await page.goto("/admin/settings");
  await page.getByLabel("Timezone IANA").fill("America/Bahia");
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Data local da empresa:")).toBeVisible();
  await page.getByLabel("Nome comercial").fill("ClientOps E2E");
  await page.getByLabel("Telefone").fill("+55 71 3000-0000");
  await page.getByLabel("E-mail de contato").fill("contact@example.com");
  await page.getByLabel("Endereço").fill("Salvador, BA");
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Cadastro completo.")).toBeVisible();

  await page.goto("/admin/settings/users");
  await page.getByLabel("Nome").fill("E2E Technician");
  await page.getByLabel("E-mail").fill(technicianEmail);
  await page.getByRole("button", { name: "Criar técnico" }).click();
  const secretCard = page
    .getByText("Senha temporária — exibida uma vez")
    .locator("..");
  await expect(secretCard).toBeVisible();
  const temporary = await secretCard.locator("code").innerText();
  expect(temporary).toHaveLength(32);
  await secretCard.getByRole("button", { name: "Fechar" }).click();
  await expect(secretCard).toBeHidden();

  const technicianRow = page
    .locator("article.user-row")
    .filter({ hasText: technicianEmail });
  await technicianRow.getByRole("button", { name: "Desabilitar" }).click();
  await expect(technicianRow).toContainText("DISABLED");
  await technicianRow.getByRole("button", { name: "Habilitar" }).click();
  await expect(technicianRow).toContainText("ACTIVE");
  await technicianRow.getByRole("button", { name: "Redefinir senha" }).click();
  await expect(secretCard).toBeVisible();
  const resetTemporary = await secretCard.locator("code").innerText();
  expect(resetTemporary).toHaveLength(32);
  expect(resetTemporary).not.toBe(temporary);
  await secretCard.getByRole("button", { name: "Fechar" }).click();
  await expect(secretCard).toBeHidden();

  await page.goto("/admin/account");
  await page.getByRole("button", { name: "Sair" }).click();
  await expect(
    page.getByRole("heading", { name: "Entrar no ClientOps" }),
  ).toBeVisible();

  await login(page, technicianEmail, temporary);
  await expect(page.getByRole("alert")).toHaveText(
    "E-mail ou senha inválidos.",
  );
  await login(page, technicianEmail, resetTemporary);
  await expect(
    page.getByRole("heading", { name: "Troque sua senha temporária" }),
  ).toBeVisible();
  await page.getByLabel("Senha atual").fill(resetTemporary);
  await page
    .getByLabel("Nova senha")
    .fill("Permanent technician password 2026!");
  await page.getByRole("button", { name: "Salvar nova senha" }).click();
  await expect(page.getByRole("heading", { name: "Hoje" })).toBeVisible();
  await page.goto("/tech/account");
  await expect(
    page.getByRole("heading", { name: "E2E Technician" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sair" }).click();
  await expect(
    page.getByRole("heading", { name: "Entrar no ClientOps" }),
  ).toBeVisible();

  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual([]);
});
