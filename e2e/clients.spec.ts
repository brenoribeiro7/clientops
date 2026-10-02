import AxeBuilder from "@axe-core/playwright";
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
  const response = page.waitForResponse(
    (candidate) =>
      candidate.url().includes("/api/v1/auth/login") &&
      candidate.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Entrar" }).click();
  await response;
  await page.waitForURL(/\/(admin|tech\/today|change-password)$/);
}

async function assertAccessible(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter(
      (violation) =>
        violation.impact === "serious" || violation.impact === "critical",
    ),
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
}

test("@cl03 fluxo real de Clients, Equipment, timeline e autorização", async ({
  page,
}, testInfo) => {
  test.setTimeout(60_000);

  const suffix = testInfo.project.name.replaceAll("-", ".");
  const clientName = `Cliente CL03 ${suffix}`;
  const updatedName = `${clientName} atualizado`;
  const equipmentName = `Equipamento ${suffix}`;
  const technicianEmail = `cl03.worker.${suffix}@example.com`;

  await login(page, adminEmail, adminPassword);
  await page.goto(`/admin/clients?q=ZZ-${suffix}`);
  await expect(
    page.getByRole("heading", { name: "Nenhum cliente encontrado" }),
  ).toBeVisible();
  await page.goto("/admin/clients");
  await expect(
    page.getByRole("heading", { level: 1, name: "Clientes" }),
  ).toBeVisible();
  await assertAccessible(page);

  await page.getByRole("button", { name: "Cadastrar cliente" }).click();
  await page.getByLabel("Nome", { exact: true }).fill(clientName);
  await page.getByLabel("Telefone").fill("+55 71 3000-0303");
  await page
    .getByLabel("E-mail de contato")
    .fill(`Contato.${suffix}@example.com`);
  await page.getByLabel("Endereço").fill("Rua CL03\nSalvador");
  await page.getByLabel("Notas internas").fill("Canary CL03 privado");
  await page.getByRole("button", { name: "Cadastrar cliente" }).last().click();
  await expect(
    page.getByRole("heading", { level: 1, name: clientName }),
  ).toBeVisible();
  const clientAId = new URL(page.url()).pathname.split("/").at(-1) as string;

  await page.getByRole("button", { name: "Editar cliente" }).click();
  await page.getByLabel("Nome", { exact: true }).fill(updatedName);
  await page.getByRole("button", { name: "Salvar cliente" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: updatedName }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Adicionar equipamento" }).click();
  await page.getByLabel("Nome", { exact: true }).fill(equipmentName);
  await page.getByLabel("Marca").fill("Marca CL03");
  await page.getByLabel("Modelo").fill("Modelo inicial");
  await page.getByLabel("Número de série").fill(`SERIAL-${suffix}`);
  await page.getByLabel("Localização").fill("Sala técnica");
  await page
    .getByRole("button", { name: "Adicionar equipamento" })
    .last()
    .click();
  const equipmentCard = page
    .locator("li.resource-card")
    .filter({ hasText: equipmentName });
  await expect(equipmentCard).toBeVisible();
  await equipmentCard.getByRole("button", { name: "Editar" }).click();
  await page.getByLabel("Modelo").fill("Modelo atualizado");
  await page.getByRole("button", { name: "Salvar equipamento" }).click();
  await expect(equipmentCard).toContainText("Modelo atualizado");

  const equipmentAId = await page.evaluate(async (clientId) => {
    const response = await fetch(
      `/api/v1/clients/${clientId}/equipment?page_size=100`,
    );
    return (await response.json()).data[0].id as string;
  }, clientAId);
  await expect(page.getByText("equipment.updated")).toBeVisible();

  await equipmentCard.getByRole("button", { name: "Arquivar" }).click();
  const equipmentArchiveDialog = page.getByRole("dialog");
  await equipmentArchiveDialog
    .getByRole("button", { name: "Arquivar" })
    .click();
  await expect(equipmentCard).toBeHidden();
  await page.getByLabel("Status dos equipamentos").selectOption("ARCHIVED");
  const archivedEquipment = page
    .locator("li.resource-card")
    .filter({ hasText: equipmentName });
  await expect(archivedEquipment).toContainText("Arquivado");
  await archivedEquipment.getByRole("button", { name: "Restaurar" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Restaurar" })
    .click();
  await expect(archivedEquipment).toBeHidden();

  const clientHeader = page.locator(".detail-header");
  await clientHeader.getByRole("button", { name: "Arquivar" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Arquivar" })
    .click();
  await expect(clientHeader.getByText("Arquivado")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Adicionar equipamento" }),
  ).toBeDisabled();
  await expect(
    page.getByText("Restaure o cliente para adicionar novos equipamentos."),
  ).toBeVisible();

  await page.goto("/admin/clients?status=ARCHIVED");
  await expect(page.getByRole("link", { name: updatedName })).toBeVisible();
  await page.getByRole("link", { name: updatedName }).click();
  await clientHeader.getByRole("button", { name: "Restaurar" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Restaurar" })
    .click();
  await expect(clientHeader.getByText("Ativo")).toBeVisible();
  await assertAccessible(page);

  await page.goto("/admin/clients");
  await page.getByRole("button", { name: "Cadastrar cliente" }).click();
  const clientBName = `Cliente B ${suffix}`;
  await page.getByLabel("Nome", { exact: true }).fill(clientBName);
  await page.getByRole("button", { name: "Cadastrar cliente" }).last().click();
  await expect(
    page.getByRole("heading", { level: 1, name: clientBName }),
  ).toBeVisible();
  const clientBId = new URL(page.url()).pathname.split("/").at(-1) as string;
  const crossStatus = await page.evaluate(
    async ({ clientId, equipmentId }) =>
      (await fetch(`/api/v1/clients/${clientId}/equipment/${equipmentId}`))
        .status,
    { clientId: clientBId, equipmentId: equipmentAId },
  );
  expect(crossStatus).toBe(404);

  const technician = await page.evaluate(
    async ({ email }) => {
      const session = await (await fetch("/api/v1/auth/session")).json();
      const response = await fetch("/api/v1/users", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": session.data.csrf_token,
        },
        body: JSON.stringify({ name: "CL03 Technician", email }),
      });
      return { status: response.status, body: await response.json() };
    },
    { email: technicianEmail },
  );
  expect(technician.status).toBe(201);
  const temporary = technician.body.temporary_password as string;
  await page.goto("/admin/account");
  await page.getByRole("button", { name: "Sair" }).click();
  await login(page, technicianEmail, temporary);
  await page.getByLabel("Senha atual").fill(temporary);
  await page
    .getByLabel("Nova senha")
    .fill("Permanent CL03 technician password 2026!");
  await page.getByRole("button", { name: "Salvar nova senha" }).click();
  await expect(page.getByRole("heading", { name: "Hoje" })).toBeVisible();

  const forbidden = await page.evaluate(
    async ({ clientId, equipmentId }) => {
      const paths = [
        "/api/v1/clients",
        `/api/v1/clients/${clientId}`,
        `/api/v1/clients/${clientId}/equipment`,
        `/api/v1/clients/${clientId}/equipment/${equipmentId}`,
        `/api/v1/clients/${clientId}/timeline`,
      ];
      return Promise.all(paths.map(async (path) => (await fetch(path)).status));
    },
    { clientId: clientAId, equipmentId: equipmentAId },
  );
  expect(forbidden).toEqual([403, 403, 403, 403, 403]);
  await page.goto(`/admin/clients/${clientAId}`);
  await expect(page.getByRole("heading", { name: "Hoje" })).toBeVisible();
  await expect(page.getByText(updatedName)).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Clientes" })).toHaveCount(0);
});
