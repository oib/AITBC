import './style.css';
import {
  fetchMarketplaceOffers,
  fetchMarketplaceStats,
  submitMarketplaceBid,
  MARKETPLACE_CONFIG,
} from './lib/api';
import type { MarketplaceOffer, MarketplaceStats } from './lib/api';

const app = document.querySelector<HTMLDivElement>('#app');

if (!app) {
  throw new Error('Unable to mount marketplace app');
}

app.innerHTML = `
  <main>
    <header class="page-header">
      <p>Data mode: <strong>${MARKETPLACE_CONFIG.dataMode.toUpperCase()}</strong></p>
      <h1>Marketplace Control Center</h1>
      <p>Monitor available offers, submit bids, and review marketplace health at a glance.</p>
    </header>

    <section class="dashboard-grid" id="stats-panel">
      <article class="stat-card">
        <h2>Total Offers</h2>
        <strong id="stat-total-offers">--</strong>
        <span>Listings currently visible</span>
      </article>
      <article class="stat-card">
        <h2>Open Capacity</h2>
        <strong id="stat-open-capacity">--</strong>
        <span>GPU / compute units available</span>
      </article>
      <article class="stat-card">
        <h2>Average Price</h2>
        <strong id="stat-average-price">--</strong>
        <span>Credits per unit per hour</span>
      </article>
      <article class="stat-card">
        <h2>Active Bids</h2>
        <strong id="stat-active-bids">--</strong>
        <span>Open bids awaiting match</span>
      </article>
    </section>

    <section class="panels">
      <article class="panel" id="offers-panel">
        <h2>Available Offers</h2>
        <div id="offers-table-wrapper" class="table-wrapper">
          <p class="empty-state">Fetching marketplace offers…</p>
        </div>
      </article>

      <article class="panel">
        <h2>Submit a Bid</h2>
        <form class="bid-form" id="bid-form">
          <div>
            <label for="bid-provider">Preferred provider</label>
            <input id="bid-provider" name="provider" placeholder="Alpha Pool" required />
          </div>
          <div>
            <label for="bid-capacity">Capacity required (units)</label>
            <input id="bid-capacity" name="capacity" type="number" min="1" step="1" required />
          </div>
          <div>
            <label for="bid-price">Bid price (credits/unit/hr)</label>
            <input id="bid-price" name="price" type="number" min="0" step="0.01" required />
          </div>
          <div>
            <label for="bid-notes">Notes (optional)</label>
            <textarea id="bid-notes" name="notes" rows="3" placeholder="Add constraints, time windows, etc."></textarea>
          </div>
          <button type="submit">Submit Bid</button>
        </form>
      </article>
    </section>
  </main>
  <aside id="toast" class="toast"></aside>
`;

const selectors = {
  totalOffers: document.querySelector<HTMLSpanElement>('#stat-total-offers'),
  openCapacity: document.querySelector<HTMLSpanElement>('#stat-open-capacity'),
  averagePrice: document.querySelector<HTMLSpanElement>('#stat-average-price'),
  activeBids: document.querySelector<HTMLSpanElement>('#stat-active-bids'),
  offersWrapper: document.querySelector<HTMLDivElement>('#offers-table-wrapper'),
  bidForm: document.querySelector<HTMLFormElement>('#bid-form'),
  toast: document.querySelector<HTMLDivElement>('#toast'),
};

function formatNumber(value: number, options: Intl.NumberFormatOptions = {}): string {
  return new Intl.NumberFormat(undefined, options).format(value);
}

function renderStats(stats: MarketplaceStats): void {
  selectors.totalOffers!.textContent = formatNumber(stats.totalOffers);
  selectors.openCapacity!.textContent = `${formatNumber(stats.openCapacity)} units`;
  selectors.averagePrice!.textContent = `${formatNumber(stats.averagePrice, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} credits`; 
  selectors.activeBids!.textContent = formatNumber(stats.activeBids);
}

function statusClass(status: string): string {
  switch (status.toLowerCase()) {
    case 'open':
      return 'status-pill status-open';
    case 'reserved':
      return 'status-pill status-reserved';
    default:
      return 'status-pill';
  }
}

function renderOffers(offers: MarketplaceOffer[]): void {
  if (!selectors.offersWrapper) {
    return;
  }

  if (offers.length === 0) {
    selectors.offersWrapper.innerHTML = '<p class="empty-state">No offers available right now. Check back soon or submit a bid.</p>';
    return;
  }

  const cards = offers
    .map(
      (offer) => `
        <article class="offer-card">
          <div class="offer-card-header">
            <div class="offer-gpu-name">${offer.gpu_model || 'Unknown GPU'}</div>
            <span class="${statusClass(offer.status)}">${offer.status}</span>
          </div>
          <div class="offer-provider">${offer.provider}${offer.region ? ` · ${offer.region}` : ''}</div>
          <div class="offer-specs">
            <div class="spec-item">
              <span class="spec-label">VRAM</span>
              <span class="spec-value">${offer.gpu_memory_gb ? `${offer.gpu_memory_gb} GB` : '—'}</span>
            </div>
            <div class="spec-item">
              <span class="spec-label">GPUs</span>
              <span class="spec-value">${offer.gpu_count ?? 1}×</span>
            </div>
            <div class="spec-item">
              <span class="spec-label">CUDA</span>
              <span class="spec-value">${offer.cuda_version || '—'}</span>
            </div>
            <div class="spec-item">
              <span class="spec-label">Capacity</span>
              <span class="spec-value">${formatNumber(offer.capacity)} units</span>
            </div>
          </div>
          <div class="offer-pricing">
            <div class="offer-price">${formatNumber(offer.price_per_hour ?? offer.price, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} <small>credits/hr</small></div>
            <div class="offer-sla">${offer.sla}</div>
          </div>
        </article>
      `,
    )
    .join('');

  selectors.offersWrapper.innerHTML = `<div class="offers-grid">${cards}</div>`;
}

function showToast(message: string, duration = 2500): void {
  if (!selectors.toast) return;
  selectors.toast.textContent = message;
  selectors.toast.classList.add('visible');

  window.setTimeout(() => {
    selectors.toast?.classList.remove('visible');
  }, duration);
}

async function loadDashboard(): Promise<void> {
  try {
    const [stats, offers] = await Promise.all([
      fetchMarketplaceStats(),
      fetchMarketplaceOffers(),
    ]);

    renderStats(stats);
    renderOffers(offers);
  } catch (error) {
    console.error(error);
    if (selectors.offersWrapper) {
      selectors.offersWrapper.innerHTML = '<p class="empty-state">Failed to load offers. Please retry shortly.</p>';
    }
    showToast('Failed to load marketplace data.');
  }
}

selectors.bidForm?.addEventListener('submit', async (event) => {
  event.preventDefault();

  const formData = new FormData(selectors.bidForm!);
  const provider = formData.get('provider')?.toString().trim();
  const capacity = Number(formData.get('capacity'));
  const price = Number(formData.get('price'));
  const notes = formData.get('notes')?.toString().trim();

  if (!provider || Number.isNaN(capacity) || Number.isNaN(price)) {
    showToast('Please complete the required fields.');
    return;
  }

  try {
    selectors.bidForm!.querySelector('button')!.setAttribute('disabled', 'disabled');
    await submitMarketplaceBid({ provider, capacity, price, notes });
    selectors.bidForm!.reset();
    showToast('Bid submitted successfully!');
  } catch (error) {
    console.error(error);
    showToast('Unable to submit bid. Please try again.');
  } finally {
    selectors.bidForm!.querySelector('button')!.removeAttribute('disabled');
  }
});

loadDashboard();
