import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIResponse, type Page } from "@playwright/test";

test.use({ screenshot: "off", trace: "off", video: "off" });

const adminEmail = "admin.e2e@example.com";
const adminPassword = "ClientOps E2E admin password 2026!";

async function login(page: Page, email = adminEmail, password = adminPassword) {
  await page.goto("/login");
  const response = await page.request.post("/api/v1/auth/login", {
    data: { email, password },
    headers: {
      Origin: new URL(page.url()).origin,
      "X-ClientOps-Request": "browser-v1",
    },
  });
  expect(response.status()).toBe(200);
  await page.goto("/login");
  await page.waitForURL(/\/(admin|tech\/today|change-password)$/);
}

async function command(
  page: Page,
  method: "POST" | "PATCH",
  path: string,
  data: Record<string, unknown>,
  etag?: string,
): Promise<APIResponse> {
  const session = await (await page.request.get("/api/v1/auth/session")).json();
  return page.request.fetch(path, {
    method,
    data,
    headers: {
      Origin: new URL(page.url()).origin,
      "X-CSRF-Token": session.data.csrf_token,
      ...(etag ? { "If-Match": etag } : {}),
    },
  });
}

async function configureBusiness(
  page: Page,
  tradeName: string,
  timezone = "America/Bahia",
) {
  const current = await page.request.get("/api/v1/business-profile");
  const body = await current.json();
  const response = await command(
    page,
    "PATCH",
    "/api/v1/business-profile",
    {
      trade_name: tradeName,
      phone: "+55 71 3000-0404",
      email: "public-business@example.com",
      address: "Rua Pública CL04, Salvador",
      timezone,
      acknowledge_timezone_change:
        body.data.timezone !== null && body.data.timezone !== timezone,
    },
    current.headers()["etag"],
  );
  expect(response.status()).toBe(200);
}

async function createClient(page: Page, name: string) {
  const response = await command(page, "POST", "/api/v1/clients", {
    name,
    phone: "client-phone-pii-canary",
    email: "client-email-pii-canary@example.com",
    address: "client-address-pii-canary",
    notes: "client-notes-pii-canary",
  });
  expect(response.status()).toBe(201);
  return (await response.json()).data as { id: string; name: string };
}

async function createAndSend(page: Page, clientId: string, validUntil: string) {
  const created = await command(page, "POST", "/api/v1/quotes", {
    client_id: clientId,
    valid_until: validUntil,
    notes: "Ciclo auxiliar CL04",
    items: [
      {
        position: 1,
        description: "Serviço auxiliar",
        quantity: "1.000",
        unit_price: "1.00",
      },
    ],
  });
  expect(created.status()).toBe(201);
  const quote = (await created.json()).data as { id: string };
  const sent = await command(
    page,
    "POST",
    `/api/v1/quotes/${quote.id}/send`,
    {},
    created.headers()["etag"],
  );
  expect(sent.status()).toBe(200);
  return { quote, sent: await sent.json() };
}

function bearerFrom(shareUrl: string) {
  return new URL(shareUrl).hash.slice("#token=".length);
}

function dateInZone(timeZone: string, daysAhead: number) {
  const instant = new Date(Date.now() + daysAhead * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(instant);
}

test("@cl04 fluxo Admin, aprovação pública, snapshot e ciclo de acesso", async ({
  browser,
  page,
}, testInfo) => {
  test.setTimeout(90_000);
  const suffix = testInfo.project.name.replaceAll("-", ".");
  const originalBusiness = `Empresa CL04 ${suffix}`;
  const originalClient = `Cliente CL04 ${suffix}`;
  const changedClient = `${originalClient} alterado`;
  const validUntil = dateInZone("America/Bahia", 1);

  await login(page);
  await configureBusiness(page, originalBusiness, "Etc/GMT+12");
  const client = await createClient(page, originalClient);
  const expiring = await createAndSend(
    page,
    client.id,
    dateInZone("Etc/GMT+12", 0),
  );
  await configureBusiness(page, originalBusiness, "America/Bahia");

  await page.goto("/admin/quotes");
  await expect(
    page.getByRole("heading", { level: 1, name: "Orçamentos" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Novo orçamento" }).click();
  await page
    .getByLabel("Cliente ativo")
    .selectOption({ label: originalClient });
  await page.getByLabel("Validade").fill(validUntil);
  await page
    .getByLabel("Observações da proposta")
    .fill("Proposta histórica CL04");
  await page.getByRole("button", { name: "Adicionar item" }).click();
  await page.getByLabel("Descrição do item 1").fill("Manutenção preventiva");
  await page.getByLabel("Quantidade").fill("1.005");
  await page.getByLabel("Preço unitário").fill("10.00");
  await page.getByRole("button", { name: "Criar rascunho" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: /ORC-/ }),
  ).toBeVisible();
  await expect(page.getByText("R$ 10,05").last()).toBeVisible();
  const heroQuoteId = new URL(page.url()).pathname.split("/").at(-1) as string;

  await page.getByRole("button", { name: "Editar" }).click();
  await page
    .getByLabel("Observações da proposta")
    .fill("Minha edição local preservada");
  const concurrent = await page.request.get(`/api/v1/quotes/${heroQuoteId}`);
  const concurrentPatch = await command(
    page,
    "PATCH",
    `/api/v1/quotes/${heroQuoteId}`,
    { notes: "Alteração concorrente" },
    concurrent.headers()["etag"],
  );
  expect(concurrentPatch.status()).toBe(200);
  await page.getByRole("button", { name: "Salvar orçamento" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "formulário foi preservado",
  );
  await expect(page.getByLabel("Observações da proposta")).toHaveValue(
    "Minha edição local preservada",
  );
  await page.getByRole("button", { name: "Recarregar versão atual" }).click();
  await expect(page.getByLabel("Observações da proposta")).toHaveValue(
    "Alteração concorrente",
  );
  await page
    .getByLabel("Observações da proposta")
    .fill("Proposta histórica CL04");
  await page.getByRole("button", { name: "Salvar orçamento" }).click();
  await expect(page.getByText("Orçamento salvo.")).toBeVisible();

  await page.getByRole("button", { name: "Enviar orçamento" }).click();
  await expect(
    page.getByText("Confirma o envio deste orçamento?"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirmar e enviar" }).click();
  const shareInput = page.getByLabel("Link do orçamento");
  await expect(shareInput).toBeVisible();
  const shareUrl = await shareInput.inputValue();
  const bearer = bearerFrom(shareUrl);
  expect(bearer).toHaveLength(43);

  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Abrir WhatsApp" }).click();
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded").catch(() => undefined);
  expect(popup.url()).not.toContain(bearer);
  expect(popup.url()).toMatch(/(?:wa\.me|whatsapp\.com)/);
  await popup.close();
  await page.getByRole("button", { name: "Fechar" }).click();
  await expect(shareInput).toHaveCount(0);

  const currentClient = await page.request.get(`/api/v1/clients/${client.id}`);
  const clientPatch = await command(
    page,
    "PATCH",
    `/api/v1/clients/${client.id}`,
    { name: changedClient },
    currentClient.headers()["etag"],
  );
  expect(clientPatch.status()).toBe(200);
  await configureBusiness(
    page,
    `${originalBusiness} alterada`,
    "Pacific/Kiritimati",
  );

  const historical = await page.request.get(`/api/v1/quotes/${heroQuoteId}`);
  const historicalBody = (await historical.json()).data;
  expect(historicalBody.commercial_snapshot.client.name).toBe(originalClient);
  expect(historicalBody.commercial_snapshot.business.trade_name).toBe(
    originalBusiness,
  );
  expect(historicalBody.commercial_snapshot.quote.business_timezone).toBe(
    "America/Bahia",
  );
  expect(historicalBody.is_expired).toBe(false);

  const origin = new URL(page.url()).origin;
  const publicContext = await browser.newContext({
    baseURL: origin,
    ignoreHTTPSErrors: true,
  });
  const publicPage = await publicContext.newPage();
  const consoleMessages: string[] = [];
  publicPage.on("console", (message) => consoleMessages.push(message.text()));
  const navigation = await publicPage.goto(shareUrl);
  const publicHeaders = navigation?.headers() ?? {};
  expect(publicHeaders["cache-control"]).toContain("no-store");
  expect(publicHeaders["referrer-policy"]).toBe("no-referrer");
  expect(publicHeaders["x-content-type-options"]).toBe("nosniff");
  expect(publicHeaders["x-frame-options"]).toBe("DENY");
  expect(publicHeaders["content-security-policy"]).toContain(
    "default-src 'self'",
  );
  expect(publicHeaders["content-security-policy"]).not.toContain(
    "script-src 'unsafe-inline'",
  );
  await expect(publicPage).toHaveURL(`${origin}/q`);
  await expect(
    publicPage.getByRole("heading", { name: originalBusiness }),
  ).toBeVisible();
  await expect(publicPage.getByText(new RegExp(originalClient))).toBeVisible();
  await expect(publicPage.getByText("Manutenção preventiva")).toBeVisible();
  await expect(publicPage.getByText("R$ 10,05").last()).toBeVisible();
  const publicHtml = await publicPage.locator("html").innerHTML();
  for (const canary of [
    bearer,
    client.id,
    changedClient,
    "client-phone-pii-canary",
    "client-email-pii-canary@example.com",
    "client-address-pii-canary",
    "client-notes-pii-canary",
  ]) {
    expect(publicHtml).not.toContain(canary);
  }
  expect(await publicPage.evaluate(() => Object.keys(localStorage))).toEqual(
    [],
  );
  expect(await publicPage.evaluate(() => Object.keys(sessionStorage))).toEqual(
    [],
  );
  expect(
    await publicPage.evaluate(async () =>
      (await indexedDB.databases()).map((database) => database.name),
    ),
  ).toEqual([]);
  expect(await publicPage.evaluate(() => location.hash)).toBe("");
  expect(await publicPage.evaluate(() => document.referrer)).not.toContain(
    bearer,
  );
  expect(consoleMessages.join("\n")).not.toContain(bearer);
  expect(
    await publicPage.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const accessibility = await new AxeBuilder({ page: publicPage }).analyze();
  expect(
    accessibility.violations.filter((item) =>
      ["serious", "critical"].includes(item.impact ?? ""),
    ),
  ).toEqual([]);
  const sentProjection = await publicContext.request.get(
    "/api/v1/public/quote",
    {
      headers: { Authorization: `Bearer ${bearer}` },
    },
  );
  const sentBody = (await sentProjection.json()).data;
  expect(Object.keys(sentBody.client)).toEqual(["name"]);
  expect(sentBody.business_today).toBe(dateInZone("Pacific/Kiritimati", 0));
  expect(sentBody.is_expired).toBe(false);

  await publicPage.getByRole("button", { name: "Aprovar orçamento" }).click();
  await expect(
    publicPage.getByRole("heading", { name: "Confirmar aprovação" }),
  ).toBeVisible();
  await publicPage.getByRole("button", { name: "Confirmar aprovação" }).click();
  const approved = publicPage.getByText(/Orçamento aprovado em/);
  await expect(approved).toBeVisible();
  const approvedText = await approved.textContent();
  const repeat = await publicContext.request.post(
    "/api/v1/public/quote/approve",
    {
      data: { accept: true },
      headers: { Authorization: `Bearer ${bearer}`, Origin: origin },
    },
  );
  expect(repeat.status()).toBe(200);
  expect((await repeat.json()).data.status).toBe("APPROVED");
  await expect(approved).toHaveText(approvedText ?? "");

  const forwarded = await publicContext.request.get("/api/v1/public/quote", {
    headers: {
      Authorization: `Bearer ${bearer}`,
      "X-Forwarded-For": "203.0.113.40",
    },
  });
  expect(forwarded.status()).toBe(200);
  const forwardedBody = (await forwarded.json()).data;
  expect(forwardedBody.status).toBe("APPROVED");
  expect(Object.keys(forwardedBody.client)).toEqual(["name"]);
  expect(JSON.stringify(forwardedBody)).not.toContain(
    "client-phone-pii-canary",
  );
  await page.goto(`/admin/quotes/${heroQuoteId}`);
  await expect(page.locator(".status-badge")).toHaveText("APPROVED");
  await publicPage.reload();
  await expect(
    publicPage.getByRole("heading", { name: "Orçamento indisponível" }),
  ).toBeVisible();
  await publicContext.close();

  const expiredContext = await browser.newContext({
    baseURL: origin,
    ignoreHTTPSErrors: true,
  });
  const expiredBearer = bearerFrom(expiring.sent.public_access.share_url);
  const expiredProjection = await expiredContext.request.get(
    "/api/v1/public/quote",
    { headers: { Authorization: `Bearer ${expiredBearer}` } },
  );
  expect(expiredProjection.status()).toBe(200);
  expect((await expiredProjection.json()).data.is_expired).toBe(true);
  const expiredPage = await expiredContext.newPage();
  await expiredPage.goto(expiring.sent.public_access.share_url);
  await expect(expiredPage.getByText("Este orçamento venceu.")).toBeVisible();
  await expect(
    expiredPage.getByRole("button", { name: "Aprovar orçamento" }),
  ).toHaveCount(0);
  const expiredApproval = await expiredContext.request.post(
    "/api/v1/public/quote/approve",
    {
      data: { accept: true },
      headers: {
        Authorization: `Bearer ${expiredBearer}`,
        Origin: origin,
      },
    },
  );
  expect(expiredApproval.status()).toBe(409);
  await expiredContext.close();

  const invalidContext = await browser.newContext({
    baseURL: origin,
    ignoreHTTPSErrors: true,
  });
  const invalidPage = await invalidContext.newPage();
  await invalidPage.goto("/q#token=invalid");
  await expect(
    invalidPage.getByRole("heading", { name: "Orçamento indisponível" }),
  ).toBeVisible();
  expect(await invalidPage.evaluate(() => location.hash)).toBe("");
  const invalidJson = await invalidContext.request.get("/api/v1/public/quote", {
    headers: { Authorization: "Bearer invalid-bearer-canary" },
  });
  expect(invalidJson.status()).toBe(401);
  expect(await invalidJson.text()).not.toContain("invalid-bearer-canary");
  await invalidContext.close();

  const rotating = await createAndSend(page, client.id, validUntil);
  const oldUrl = rotating.sent.public_access.share_url as string;
  const oldBearer = bearerFrom(oldUrl);
  const rotated = await command(
    page,
    "POST",
    `/api/v1/quotes/${rotating.quote.id}/public-access`,
    {
      expected_access_id: rotating.sent.public_access.id,
    },
  );
  expect(rotated.status()).toBe(200);
  const rotatedBody = await rotated.json();
  const newBearer = bearerFrom(rotatedBody.data.share_url);
  expect(
    (
      await page.request.get("/api/v1/public/quote", {
        headers: { Authorization: `Bearer ${oldBearer}` },
      })
    ).status(),
  ).toBe(401);
  expect(
    (
      await page.request.get("/api/v1/public/quote", {
        headers: { Authorization: `Bearer ${newBearer}` },
      })
    ).status(),
  ).toBe(200);
  const revoked = await command(
    page,
    "POST",
    `/api/v1/quotes/${rotating.quote.id}/public-access/${rotatedBody.data.id}/revoke`,
    {},
  );
  expect(revoked.status()).toBe(200);
  expect(
    (
      await page.request.get("/api/v1/public/quote", {
        headers: { Authorization: `Bearer ${newBearer}` },
      })
    ).status(),
  ).toBe(401);

  const cancelling = await createAndSend(page, client.id, validUntil);
  const cancelledBearer = bearerFrom(cancelling.sent.public_access.share_url);
  const currentQuote = await page.request.get(
    `/api/v1/quotes/${cancelling.quote.id}`,
  );
  const cancelled = await command(
    page,
    "POST",
    `/api/v1/quotes/${cancelling.quote.id}/cancel`,
    { reason: "Cancelamento E2E CL04" },
    currentQuote.headers()["etag"],
  );
  expect(cancelled.status()).toBe(200);
  expect(
    (
      await page.request.get("/api/v1/public/quote", {
        headers: { Authorization: `Bearer ${cancelledBearer}` },
      })
    ).status(),
  ).toBe(401);

  const technicianEmail = `cl04.tech.${suffix}@example.com`;
  const technician = await command(page, "POST", "/api/v1/users", {
    name: "CL04 Technician",
    email: technicianEmail,
  });
  expect(technician.status()).toBe(201);
  const temporary = (await technician.json()).temporary_password as string;
  const technicianContext = await browser.newContext({
    baseURL: origin,
    ignoreHTTPSErrors: true,
  });
  const loginResponse = await technicianContext.request.post(
    "/api/v1/auth/login",
    {
      data: { email: technicianEmail, password: temporary },
      headers: { Origin: origin, "X-ClientOps-Request": "browser-v1" },
    },
  );
  expect(loginResponse.status()).toBe(200);
  const technicianSession = (await loginResponse.json()).data;
  const changed = await technicianContext.request.post(
    "/api/v1/auth/change-password",
    {
      data: {
        current_password: temporary,
        new_password: "Permanent CL04 technician password 2026!",
      },
      headers: { Origin: origin, "X-CSRF-Token": technicianSession.csrf_token },
    },
  );
  expect(changed.status()).toBe(200);
  expect((await technicianContext.request.get("/api/v1/quotes")).status()).toBe(
    403,
  );
  const technicianPage = await technicianContext.newPage();
  await technicianPage.goto(`/admin/quotes/${rotating.quote.id}`);
  await expect(
    technicianPage.getByRole("heading", { name: "Hoje" }),
  ).toBeVisible();
  await expect(
    technicianPage.getByRole("link", { name: "Orçamentos" }),
  ).toHaveCount(0);
  await technicianContext.close();
});
