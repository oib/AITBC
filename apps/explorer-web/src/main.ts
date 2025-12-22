import "../public/css/theme.css";
import "../public/css/base.css";
import "../public/css/layout.css";
import { siteHeader } from "./components/siteHeader";
import { siteFooter } from "./components/siteFooter";
import { overviewTitle, renderOverviewPage, initOverviewPage } from "./pages/overview";
import { blocksTitle, renderBlocksPage, initBlocksPage } from "./pages/blocks";
import { transactionsTitle, renderTransactionsPage, initTransactionsPage } from "./pages/transactions";
import { addressesTitle, renderAddressesPage, initAddressesPage } from "./pages/addresses";
import { receiptsTitle, renderReceiptsPage, initReceiptsPage } from "./pages/receipts";
import { initDataModeToggle } from "./components/dataModeToggle";
import { getDataMode } from "./lib/mockData";
import { initNotifications } from "./components/notifications";

type PageConfig = {
  title: string;
  render: () => string;
  init?: () => void | Promise<void>;
};

const overviewConfig: PageConfig = {
  title: overviewTitle,
  render: renderOverviewPage,
  init: initOverviewPage,
};

const routes: Record<string, PageConfig> = {
  "/": overviewConfig,
  "/index.html": overviewConfig,
  "/blocks": {
    title: blocksTitle,
    render: renderBlocksPage,
    init: initBlocksPage,
  },
  "/transactions": {
    title: transactionsTitle,
    render: renderTransactionsPage,
    init: initTransactionsPage,
  },
  "/addresses": {
    title: addressesTitle,
    render: renderAddressesPage,
    init: initAddressesPage,
  },
  "/receipts": {
    title: receiptsTitle,
    render: renderReceiptsPage,
    init: initReceiptsPage,
  },
};

function render(): void {
  initNotifications();
  const root = document.querySelector<HTMLDivElement>("#app");
  if (!root) {
    console.warn("[Explorer] Missing #app root element");
    return;
  }

  const currentPath = window.location.pathname.replace(/\/$/, "");
  // Remove /explorer prefix for routing
  const normalizedPath = currentPath.replace(/^\/explorer/, "") || "/";
  const page = routes[normalizedPath] ?? null;

  root.innerHTML = `
    ${siteHeader(page?.title ?? "Explorer")}
    <main class="page">${(page ?? notFoundPageConfig).render()}</main>
    ${siteFooter()}
  `;

  initDataModeToggle(render);
  void page?.init?.();
}

const notFoundPageConfig: PageConfig = {
  title: "Not Found",
  render: () => `
    <section class="not-found">
      <h2>Page Not Found</h2>
      <p>The requested view is not available yet.</p>
    </section>
  `,
};

document.addEventListener("DOMContentLoaded", render);
