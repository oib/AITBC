export function siteHeader(title: string): string {
  return `
    <header class="site-header">
      <div class="site-header__inner">
        <a class="site-header__brand" href="/">AITBC Explorer</a>
        <h1 class="site-header__title">${title}</h1>
        <div class="site-header__controls">
          <div data-role="data-mode-toggle"></div>
        </div>
        <nav class="site-header__nav">
          <a href="/">Overview</a>
          <a href="/blocks">Blocks</a>
          <a href="/transactions">Transactions</a>
          <a href="/addresses">Addresses</a>
          <a href="/receipts">Receipts</a>
        </nav>
      </div>
    </header>
  `;
}
