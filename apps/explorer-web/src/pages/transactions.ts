import {
  fetchTransactions,
  type TransactionSummary,
} from "../lib/mockData";

export const transactionsTitle = "Transactions";

export function renderTransactionsPage(): string {
  return `
    <section class="transactions">
      <header class="section-header">
        <h2>Recent Transactions</h2>
        <p class="lead">Mock data is shown below until coordinator or node APIs are wired up.</p>
      </header>
      <table class="table transactions__table">
        <thead>
          <tr>
            <th scope="col">Hash</th>
            <th scope="col">Block</th>
            <th scope="col">From</th>
            <th scope="col">To</th>
            <th scope="col">Value</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody id="transactions-table-body">
          <tr>
            <td class="placeholder" colspan="6">Loading transactions…</td>
          </tr>
        </tbody>
      </table>
    </section>
  `;
}

export async function initTransactionsPage(): Promise<void> {
  const tbody = document.querySelector<HTMLTableSectionElement>(
    "#transactions-table-body",
  );
  if (!tbody) {
    return;
  }

  const transactions = await fetchTransactions();
  if (transactions.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td class="placeholder" colspan="6">No mock transactions available.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = transactions.map(renderTransactionRow).join("");
}

function renderTransactionRow(tx: TransactionSummary): string {
  return `
    <tr>
      <td><code>${tx.hash.slice(0, 18)}…</code></td>
      <td>${tx.block}</td>
      <td><code>${tx.from.slice(0, 12)}…</code></td>
      <td><code>${tx.to.slice(0, 12)}…</code></td>
      <td>${tx.value}</td>
      <td>${tx.status}</td>
    </tr>
  `;
}
