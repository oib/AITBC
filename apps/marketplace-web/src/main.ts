// Type declarations for global objects
declare global {
  interface Window {
    analytics?: {
      track: (event: string, data: any) => void;
    };
  }
}

import './style.css';
import {
  fetchMarketplaceOffers,
  fetchMarketplaceStats,
  submitMarketplaceBid,
} from './lib/api';
import type { MarketplaceOffer, MarketplaceStats } from './lib/api';

const app = document.querySelector<HTMLDivElement>('#app');

if (!app) {
  throw new Error('Unable to mount marketplace app');
}

app.innerHTML = `
  <main>
    <header class="page-header">
      <nav class="page-header__nav">
        <a href="/" class="back-link">← Home</a>
        <a href="/explorer/">Explorer</a>
        <a href="/Exchange/">Exchange</a>
      </nav>
      <div class="page-header-content">
        <div class="page-header-title">
          <h1>Marketplace Control Center</h1>
          <p>Monitor available offers, submit bids, and review marketplace health at a glance.</p>
        </div>
        <button onclick="toggleDarkMode()" class="dark-mode-toggle" title="Toggle dark mode">
          <span id="darkModeEmoji">🌙</span>
          <span id="darkModeText">Dark</span>
        </button>
      </div>
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
    <section id="stats-grid">

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
  totalOffers: document.querySelector<HTMLSpanElement>('#stat-total-offers')!,
  openCapacity: document.querySelector<HTMLSpanElement>('#stat-open-capacity')!,
  averagePrice: document.querySelector<HTMLSpanElement>('#stat-average-price')!,
  activeBids: document.querySelector<HTMLSpanElement>('#stat-active-bids')!,
  statsWrapper: document.querySelector<HTMLDivElement>('#stats-grid')!,
  offersWrapper: document.querySelector<HTMLDivElement>('#offers-table-wrapper')!,
  bidForm: document.querySelector<HTMLFormElement>('#bid-form')!,
  toast: document.querySelector<HTMLDivElement>('#toast')!,
};

function formatNumber(value: number, options: Intl.NumberFormatOptions = {}): string {
  return new Intl.NumberFormat(undefined, options).format(value);
}

function renderStats(stats: MarketplaceStats): void {
  selectors.totalOffers.textContent = formatNumber(stats.totalOffers);
  selectors.openCapacity.textContent = `${formatNumber(stats.openCapacity)} units`;
  selectors.averagePrice.textContent = `${formatNumber(stats.averagePrice, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} credits`; 
  selectors.activeBids.textContent = formatNumber(stats.activeBids);
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
  const wrapper = selectors.offersWrapper;
  if (!wrapper) return;

  if (offers.length === 0) {
    wrapper.innerHTML = '<p class="empty-state">No offers available right now. Check back soon or submit a bid.</p>';
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
          ${offer.attributes?.models?.length ? `
          <div class="offer-plugins">
            <span class="plugin-badge">Ollama</span>
          </div>
          <div class="offer-models">
            <span class="models-label">Available Models</span>
            <div class="model-tags">${offer.attributes.models.map((m: string) => `<span class="model-tag">${m}</span>`).join('')}</div>
          </div>` : ''}
          <div class="offer-pricing">
            <div class="offer-price">${formatNumber(offer.price_per_hour ?? offer.price, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} <small>credits/hr</small></div>
            <div class="offer-sla">${offer.sla}</div>
          </div>
        </article>
      `,
    )
    .join('');

  wrapper.innerHTML = `<div class="offers-grid">${cards}</div>`;
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
  // Show skeleton loading states
  showSkeletons();
  
  try {
    const [stats, offers] = await Promise.all([
      fetchMarketplaceStats(),
      fetchMarketplaceOffers(),
    ]);

    renderStats(stats);
    renderOffers(offers);
  } catch (error) {
    console.error(error);
    const wrapper = selectors.offersWrapper;
    if (wrapper) {
      wrapper.innerHTML = '<p class="empty-state">Failed to load offers. Please retry shortly.</p>';
    }
    showToast('Failed to load marketplace data.');
  }
}

function showSkeletons() {
  const statsWrapper = selectors.statsWrapper;
  const offersWrapper = selectors.offersWrapper;
  
  if (statsWrapper) {
    statsWrapper.innerHTML = `
      <div class="skeleton-grid">
        ${Array(4).fill('').map(() => `
          <div class="skeleton skeleton-card"></div>
        `).join('')}
      </div>
    `;
  }
  
  if (offersWrapper) {
    offersWrapper.innerHTML = `
      <div class="skeleton-list">
        ${Array(6).fill('').map(() => `
          <div class="skeleton skeleton-card"></div>
        `).join('')}
      </div>
    `;
  }
}

selectors.bidForm?.addEventListener('submit', async (event) => {
  event.preventDefault();

  const form = selectors.bidForm;
  if (!form) return;

  const formData = new FormData(form);
  const provider = formData.get('provider')?.toString().trim();
  const capacity = Number(formData.get('capacity'));
  const price = Number(formData.get('price'));
  const notes = formData.get('notes')?.toString().trim();

  if (!provider || Number.isNaN(capacity) || Number.isNaN(price)) {
    showToast('Please complete the required fields.');
    return;
  }

  try {
    const submitButton = form.querySelector('button');
    if (submitButton) {
      submitButton.setAttribute('disabled', 'disabled');
    }
    
    await submitMarketplaceBid({ provider, capacity, price, notes });
    form.reset();
    showToast('Bid submitted successfully!');
  } catch (error) {
    console.error(error);
    showToast('Unable to submit bid. Please try again.');
  } finally {
    const submitButton = form.querySelector('button');
    if (submitButton) {
      submitButton.removeAttribute('disabled');
    }
  }
});

loadDashboard();

// Dark mode functionality with system preference detection
function toggleDarkMode() {
  const currentTheme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  setTheme(newTheme);
}

function setTheme(theme: string) {
  // Apply theme immediately
  if (theme === 'dark') {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
  
  // Save to localStorage for persistence
  localStorage.setItem('marketplaceTheme', theme);
  
  // Update button display
  updateThemeButton(theme);
  
  // Send analytics event if available
  if (typeof window !== 'undefined' && window.analytics) {
    window.analytics.track('marketplace_theme_changed', { theme });
  }
}

function updateThemeButton(theme: string) {
  const emoji = document.getElementById('darkModeEmoji');
  const text = document.getElementById('darkModeText');
  
  if (emoji && text) {
    if (theme === 'dark') {
      emoji.textContent = '🌙';
      text.textContent = 'Dark';
    } else {
      emoji.textContent = '☀️';
      text.textContent = 'Light';
    }
  }
}

function getPreferredTheme(): string {
  // 1. Check localStorage first (user preference for marketplace)
  const saved = localStorage.getItem('marketplaceTheme');
  if (saved) {
    return saved;
  }
  
  // 2. Check main site preference for consistency
  const mainSiteTheme = localStorage.getItem('theme');
  if (mainSiteTheme) {
    return mainSiteTheme;
  }
  
  // 3. Check system preference
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  
  // 4. Default to dark (AITBC brand preference)
  return 'dark';
}

function initializeTheme() {
  const theme = getPreferredTheme();
  setTheme(theme);
  
  // Listen for system preference changes
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      // Only auto-switch if user hasn't manually set a preference
      if (!localStorage.getItem('marketplaceTheme') && !localStorage.getItem('theme')) {
        setTheme(e.matches ? 'dark' : 'light');
      }
    });
  }
}

// Initialize theme immediately (before DOM loads)
initializeTheme();

// Reference to suppress TypeScript "never used" warning
// @ts-ignore - function called from HTML onclick
window.toggleDarkMode = toggleDarkMode;
