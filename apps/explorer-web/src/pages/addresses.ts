import { fetchAddresses, type AddressSummary } from "../lib/mockData";

export const addressesTitle = "Addresses";

export function renderAddressesPage(): string {
  return `
    <section class="addresses">
      <header class="section-header">
        <h2>Address Lookup</h2>
        <p class="lead">Enter an account address to view recent transactions, balances, and receipt history (mock results shown below).</p>
      </header>
      <form class="addresses__search" aria-label="Search for an address">
        <label class="addresses__label" for="address-input">Address</label>
        <div class="addresses__input-group">
          <input id="address-input" name="address" type="search" placeholder="0x..." disabled />
          <button type="submit" disabled>Search</button>
        </div>
        <p class="placeholder">Searching will be enabled after integrating the coordinator/blockchain node endpoints.</p>
      </form>
      <section class="addresses__details">
        <h3>Recent Activity</h3>
        <table class="table addresses__table">
          <thead>
            <tr>
              <th scope="col">Address</th>
              <th scope="col">Balance</th>
              <th scope="col">Tx Count</th>
              <th scope="col">Last Active</th>
            </tr>
          </thead>
          <tbody id="addresses-table-body">
            <tr>
              <td class="placeholder" colspan="4">Loading addresses…</td>
            </tr>
          </tbody>
        </table>
      </section>
    </section>
  `;
}

export async function initAddressesPage(): Promise<void> {
  const tbody = document.querySelector<HTMLTableSectionElement>(
    "#addresses-table-body",
  );
  if (!tbody) {
    return;
  }

  const addresses = await fetchAddresses();
  if (addresses.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td class="placeholder" colspan="4">No mock addresses available.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = addresses.map(renderAddressRow).join("");
}

function renderAddressRow(address: AddressSummary): string {
  return `
    <tr>
      <td><code>${address.address}</code></td>
      <td>${address.balance}</td>
      <td>${address.txCount}</td>
      <td>${new Date(address.lastActive).toLocaleString()}</td>
    </tr>
  `;
}
