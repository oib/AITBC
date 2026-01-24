import {
  fetchBlocks,
  fetchTransactions,
  fetchReceipts,
} from "../lib/mockData";

export const overviewTitle = "Network Overview";

export function renderOverviewPage(): string {
  return `
    <section class="overview">
      <p class="lead">Real-time AITBC network statistics and activity.</p>
      <div class="overview__grid">
        <article class="card">
          <h3>Latest Block</h3>
          <ul class="stat-list" id="overview-block-stats">
            <li class="placeholder">Loading block data…</li>
          </ul>
        </article>
        <article class="card">
          <h3>Recent Transactions</h3>
          <ul class="stat-list" id="overview-transaction-stats">
            <li class="placeholder">Loading transaction data…</li>
          </ul>
        </article>
        <article class="card">
          <h3>Receipt Metrics</h3>
          <ul class="stat-list" id="overview-receipt-stats">
            <li class="placeholder">Loading receipt data…</li>
          </ul>
        </article>
      </div>
    </section>
  `;
}

export async function initOverviewPage(): Promise<void> {
  const [blocks, transactions, receipts] = await Promise.all([
    fetchBlocks(),
    fetchTransactions(),
    fetchReceipts(),
  ]);
  const blockStats = document.querySelector<HTMLUListElement>(
    "#overview-block-stats",
  );
  if (blockStats) {
    if (blocks && blocks.length > 0) {
      const latest = blocks[0];
      blockStats.innerHTML = `
        <li><strong>Height:</strong> ${latest.height}</li>
        <li><strong>Hash:</strong> ${latest.hash.slice(0, 18)}…</li>
        <li><strong>Proposer:</strong> <code>${latest.proposer.slice(0, 18)}…</code></li>
        <li><strong>Time:</strong> ${new Date(latest.timestamp).toLocaleString()}</li>
      `;
    } else {
      blockStats.innerHTML = `
        <li class="placeholder">No blocks available.</li>
      `;
    }
  }
  const txStats = document.querySelector<HTMLUListElement>("#overview-transaction-stats");
  if (txStats) {
    if (transactions && transactions.length > 0) {
      const succeeded = transactions.filter((tx) => tx.status === "Succeeded" || tx.status === "Completed");
      const running = transactions.filter((tx) => tx.status === "Running");
      txStats.innerHTML = `
        <li><strong>Total:</strong> ${transactions.length}</li>
        <li><strong>Completed:</strong> ${succeeded.length}</li>
        <li><strong>Running:</strong> ${running.length}</li>
      `;
    } else {
      txStats.innerHTML = `<li class="placeholder">No transactions available.</li>`;
    }
  }

  const receiptStats = document.querySelector<HTMLUListElement>(
    "#overview-receipt-stats",
  );
  if (receiptStats) {
    if (receipts && receipts.length > 0) {
      const attested = receipts.filter((receipt) => receipt.status === "Attested");
      receiptStats.innerHTML = `
        <li><strong>Total Receipts:</strong> ${receipts.length}</li>
        <li><strong>Attested:</strong> ${attested.length}</li>
        <li><strong>Pending:</strong> ${receipts.length - attested.length}</li>
      `;
    } else {
      receiptStats.innerHTML = `<li class="placeholder">No receipts available. Try switching data mode.</li>`;
    }
  }
}
