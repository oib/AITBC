import { fetchBlocks, type BlockSummary } from "../lib/mockData";

export const blocksTitle = "Blocks";

export function renderBlocksPage(): string {
  return `
    <section class="blocks">
      <header class="section-header">
        <h2>Recent Blocks</h2>
        <p class="lead">This view lists blocks pulled from the coordinator or blockchain node (mock data shown for now).</p>
      </header>
      <table class="table blocks__table">
        <thead>
          <tr>
            <th scope="col">Height</th>
            <th scope="col">Block Hash</th>
            <th scope="col">Timestamp</th>
            <th scope="col">Tx Count</th>
            <th scope="col">Proposer</th>
          </tr>
        </thead>
        <tbody id="blocks-table-body">
          <tr>
            <td class="placeholder" colspan="5">Loading blocks…</td>
          </tr>
        </tbody>
      </table>
    </section>
  `;
}

export async function initBlocksPage(): Promise<void> {
  const tbody = document.querySelector<HTMLTableSectionElement>(
    "#blocks-table-body",
  );
  if (!tbody) {
    return;
  }

  const blocks = await fetchBlocks();
  if (blocks.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td class="placeholder" colspan="5">No mock blocks available.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = blocks
    .map((block) => renderBlockRow(block))
    .join("");
}

function renderBlockRow(block: BlockSummary): string {
  return `
    <tr>
      <td>${block.height}</td>
      <td><code>${block.hash.slice(0, 18)}…</code></td>
      <td>${new Date(block.timestamp).toLocaleString()}</td>
      <td>${block.txCount}</td>
      <td>${block.proposer}</td>
    </tr>
  `;
}
