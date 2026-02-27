(function () {
  // Immediately restore theme on script load
  const savedTheme = localStorage.getItem('theme') || localStorage.getItem('exchangeTheme');
  if (savedTheme) {
    if (savedTheme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
      document.documentElement.classList.remove('dark');
    }
  }

  const NAV_ITEMS = [
    { key: 'home', label: 'Home', href: '/' },
    { key: 'explorer', label: 'Explorer', href: '/explorer/' },
    { key: 'marketplace', label: 'Marketplace', href: '/marketplace/' },
    { key: 'exchange', label: 'Exchange', href: '/Exchange/' },
    { key: 'docs', label: 'Docs', href: '/docs/index.html' },
  ];

  const CTA = { label: 'Launch Marketplace', href: '/marketplace/' };

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
          <div class="global-header__actions">
            <button type="button" class="global-dark-toggle" data-role="global-theme-toggle">
              <span class="global-dark-toggle__emoji">🌙</span>
              <span class="global-dark-toggle__text">Dark</span>
            </button>
            </div>
        </div>
      </header>
    `;
  }

  function getCurrentTheme() {
    if (document.documentElement.hasAttribute('data-theme')) {
      return document.documentElement.getAttribute('data-theme');
    }
    if (document.documentElement.classList.contains('dark')) return 'dark';
    if (document.body && document.body.classList.contains('light')) return 'light';
    return 'light';
  }

  function updateToggleLabel(theme) {
    const emojiEl = document.querySelector('.global-dark-toggle__emoji');
    const textEl = document.querySelector('.global-dark-toggle__text');
    if (!emojiEl || !textEl) return;
    if (theme === 'dark') {
      emojiEl.textContent = '🌙';
      textEl.textContent = 'Dark';
    } else {
      emojiEl.textContent = '☀️';
      textEl.textContent = 'Light';
    }
  }

    function setGlobalTheme(theme) {
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
      document.documentElement.classList.add('dark');
      document.body.classList.remove('light');
    } else {
      document.documentElement.removeAttribute('data-theme');
      document.documentElement.classList.remove('dark');
      document.body.classList.add('light');
    }
    localStorage.setItem('theme', theme);
    localStorage.setItem('exchangeTheme', theme); // for backwards compat
  }

  function getGlobalTheme() {
    return localStorage.getItem('theme') || localStorage.getItem('exchangeTheme') || 'dark';
  }

  function bindThemeToggle() {
    const toggle = document.querySelector('[data-role="global-theme-toggle"]');
    if (!toggle) return;

    toggle.addEventListener('click', () => {
      // Don't call window.toggleDarkMode anymore because it causes state desync.
      // We take full control of the global theme here.
      const current = getCurrentTheme();
      const next = current === 'dark' ? 'light' : 'dark';
      
      setGlobalTheme(next);
      
      // If the page has a specific app-level override, trigger it
      if (typeof window.setTheme === 'function' && window.location.pathname === '/') {
          window.setTheme(next);
      }

      setTimeout(() => updateToggleLabel(getCurrentTheme()), 0);
    });

    updateToggleLabel(getCurrentTheme());
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

    bindThemeToggle();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHeader);
  } else {
    initHeader();
  }
})();
