import { fetchReceipts } from "../lib/mockData";
import type { ReceiptSummary } from "../lib/models";

export const receiptsTitle = "Receipts";

export function renderReceiptsPage(): string {
  return `
    <section class="receipts">
      <header class="section-header">
        <h2>Receipt History</h2>
        <p class="lead">Live receipt data from the AITBC coordinator API.</p>
      </header>
      <div class="receipts__controls">
        <label class="receipts__label" for="job-id-input">Job ID</label>
        <div class="receipts__input-group">
          <input id="job-id-input" name="jobId" type="search" placeholder="Enter job ID" disabled />
          <button type="button" disabled>Lookup</button>
        </div>
        <p class="placeholder">Receipt lookup will be enabled after wiring to <code>/v1/jobs/{job_id}/receipts</code>.</p>
      </div>
      <section class="receipts__list">
        <h3>Recent Receipts</h3>
        <table class="table receipts__table">
          <thead>
            <tr>
              <th scope="col">Job ID</th>
              <th scope="col">Receipt ID</th>
              <th scope="col">Miner</th>
              <th scope="col">Coordinator</th>
              <th scope="col">Issued</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody id="receipts-table-body">
            <tr>
              <td class="placeholder" colspan="6">Loading receipts…</td>
            </tr>
          </tbody>
        </table>
      </section>
    </section>
  `;
}

export async function initReceiptsPage(): Promise<void> {
  const tbody = document.querySelector<HTMLTableSectionElement>(
    "#receipts-table-body",
  );
  if (!tbody) {
    return;
  }

  const receipts = await fetchReceipts();
  if (!receipts || receipts.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td class="placeholder" colspan="6">No receipts available.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = receipts.map(renderReceiptRow).join("");
}

function renderReceiptRow(receipt: ReceiptSummary): string {
  // Get jobId from receipt or from payload
  const jobId = receipt.jobId || receipt.payload?.job_id || "N/A";
  const jobIdDisplay = jobId !== "N/A" ? jobId.slice(0, 16) + "…" : "N/A";
  
  return `
    <tr>
      <td><code title="${jobId}">${jobIdDisplay}</code></td>
      <td><code title="${receipt.receiptId}">${receipt.receiptId.slice(0, 16)}…</code></td>
      <td>${receipt.miner}</td>
      <td>${receipt.coordinator}</td>
      <td>${new Date(receipt.issuedAt).toLocaleString()}</td>
      <td><span class="status-badge status-${receipt.status.toLowerCase()}">${receipt.status}</span></td>
    </tr>
  `;
}
