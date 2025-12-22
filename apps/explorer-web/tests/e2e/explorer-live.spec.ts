import { test, expect } from "@playwright/test";

test.describe("Explorer live mode", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("aitbc-explorer:data-mode", "live");
    });

    await page.route("**/v1/explorer/blocks", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              height: 12345,
              hash: "0xabcdef1234567890",
              timestamp: new Date("2024-08-22T12:00:00Z").toISOString(),
              txCount: 12,
              proposer: "validator-1",
            },
          ],
          next_offset: null,
        }),
      });
    });

    await page.route("**/v1/explorer/transactions", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              hash: "0xfeed1234",
              block: 12345,
              from: "0xAAA",
              to: "0xBBB",
              value: "0.50",
              status: "Succeeded",
            },
          ],
          next_offset: null,
        }),
      });
    });

    await page.route("**/v1/explorer/receipts", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobId: "job-1",
          items: [
            {
              receiptId: "receipt-1",
              miner: "miner-1",
              coordinator: "coordinator-1",
              issuedAt: new Date("2024-08-22T12:00:00Z").toISOString(),
              status: "Attested",
            },
          ],
        }),
      });
    });

    await page.route("**/v1/explorer/addresses", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              address: "0xADDRESS",
              balance: "100.0",
              txCount: 42,
              lastActive: new Date("2024-08-22T10:00:00Z").toISOString(),
            },
          ],
          next_offset: null,
        }),
      });
    });
  });

  test("overview renders live summaries", async ({ page }) => {
    await page.goto("/");

    await expect(page.locator("#overview-block-stats")).toContainText("12345");
    await expect(page.locator("#overview-transaction-stats")).toContainText("Total Mock Tx: 1");
    await expect(page.locator("#overview-receipt-stats")).toContainText("Total Receipts: 1");
  });

  test("blocks table shows live rows", async ({ page }) => {
    await page.goto("/blocks");

    const rows = page.locator("#blocks-table-body tr");
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("12345");
    await expect(rows.first()).toContainText("validator-1");
  });

  test("transactions table shows live rows", async ({ page }) => {
    await page.goto("/transactions");

    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("0xfeed1234");
    await expect(rows.first()).toContainText("Succeeded");
  });
});
