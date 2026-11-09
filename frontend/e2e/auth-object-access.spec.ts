import { expect, test } from "@playwright/test";

const password = "e2e-only-synthetic-password-2026";

test("login navigiert zu geschützten Objekten und verweigert fehlendes Leserecht", async ({
  browser,
  page,
}) => {
  const anonymousContext = await browser.newContext();
  const anonymousPage = await anonymousContext.newPage();
  await anonymousPage.goto("/");
  const anonymousStatus = await anonymousPage.evaluate(async () =>
    (await fetch("/api/v1/objects")).status,
  );
  expect(anonymousStatus).toBe(401);
  await anonymousContext.close();

  await page.goto("/");
  await page.getByLabel("Benutzername").fill("e2e-object-reader");
  await page.getByLabel("Passwort", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByRole("heading", { name: "Guten Tag." })).toBeVisible();

  const objectsResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/objects") && response.request().method() === "GET",
  );
  await page.getByRole("button", { name: "Objekte", exact: true }).click();
  expect((await objectsResponse).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Objekte", exact: true })).toBeVisible();
  await expect(page.getByText("E2E-Synthetisches Testobjekt", { exact: true })).toBeVisible();

  const restrictedContext = await browser.newContext();
  const restrictedPage = await restrictedContext.newPage();
  await restrictedPage.goto("/");
  await restrictedPage.getByLabel("Benutzername").fill("e2e-no-object-access");
  await restrictedPage.getByLabel("Passwort", { exact: true }).fill(password);
  await restrictedPage.getByRole("button", { name: "Anmelden" }).click();
  await expect(restrictedPage.getByRole("heading", { name: "Guten Tag." })).toBeVisible();
  await expect(
    restrictedPage.getByRole("button", { name: "Objekte", exact: true }),
  ).toHaveCount(0);

  const deniedStatus = await restrictedPage.evaluate(async () =>
    (await fetch("/api/v1/objects")).status,
  );
  expect(deniedStatus).toBe(403);
  await restrictedContext.close();
});
