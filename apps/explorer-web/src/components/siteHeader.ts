export function siteHeader(title: string): string {
  const basePath = window.location.pathname.startsWith('/explorer') ? '/explorer' : '';
  
  return `
    <header class="site-header">
      <div class="site-header__inner">
        <a class="site-header__back" href="/" title="Back to AITBC Home">← Home</a>
        <a class="site-header__brand" href="${basePath}/">AITBC Explorer</a>
        <div class="site-header__controls">
          <div data-role="data-mode-toggle"></div>
        </div>
        <nav class="site-header__nav">
          <a href="${basePath}/">Overview</a>
          <a href="${basePath}/blocks">Blocks</a>
          <a href="${basePath}/transactions">Transactions</a>
          <a href="${basePath}/addresses">Addresses</a>
          <a href="${basePath}/receipts">Receipts</a>
          <a href="/marketplace/">Marketplace</a>
        </nav>
      </div>
    </header>
  `;
}
