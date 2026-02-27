(function () {
  // Always enforce dark theme
  document.documentElement.setAttribute('data-theme', 'dark');
  document.documentElement.classList.add('dark');
  
  // Clean up any old user preferences
  if (localStorage.getItem('theme')) localStorage.removeItem('theme');
  if (localStorage.getItem('exchangeTheme')) localStorage.removeItem('exchangeTheme');

  const NAV_ITEMS = [
    { key: 'home', label: 'Home', href: '/' },
    { key: 'explorer', label: 'Explorer', href: '/explorer/' },
    { key: 'marketplace', label: 'Marketplace', href: '/marketplace/' },
    { key: 'exchange', label: 'Exchange', href: '/Exchange/' },
    { key: 'docs', label: 'Docs', href: '/docs/index.html' },
  ];

  function determineActiveKey(pathname) {
    if (pathname.startsWith('/explorer')) return 'explorer';
    if (pathname.startsWith('/marketplace')) return 'marketplace';
    if (pathname.toLowerCase().startsWith('/exchange')) return 'exchange';
    if (pathname.startsWith('/docs')) return 'docs';
    return 'home';
  }

  function buildHeader(activeKey) {
    const navLinks = NAV_ITEMS.map((item) => {
      const active = item.key === activeKey ? 'active' : '';
      return `<a href="${item.href}" class="global-nav__link ${active}">${item.label}</a>`;
    }).join('');

    return `
      <header class="global-header">
        <div class="global-header__inner">
          <a class="global-brand" href="/">
            <div class="global-brand__icon">
              <i class="fas fa-cube"></i>
            </div>
            <div class="global-brand__text">
              <span>AITBC Platform</span>
              <small>AI Blockchain Network</small>
            </div>
          </a>
          <nav class="global-nav">${navLinks}</nav>
        </div>
      </header>
    `;
  }

  function initHeader() {
    const activeKey = determineActiveKey(window.location.pathname);
    const headerHTML = buildHeader(activeKey);

    const placeholder = document.querySelector('[data-global-header]');
    const existing = placeholder || document.querySelector('.global-header');

    if (existing) {
      existing.outerHTML = headerHTML;
    } else {
      document.body.insertAdjacentHTML('afterbegin', headerHTML);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHeader);
  } else {
    initHeader();
  }
})();
