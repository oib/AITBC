# AITBC Website

Production website for the AITBC platform.

## File Structure

```
website/
├── index.html              # Homepage — platform overview & achievements
├── 404.html                # Custom error page
├── aitbc-proxy.conf        # Nginx reverse proxy configuration
├── favicon.svg
├── font-awesome-local.css
├── docs/                   # All documentation (16 pages)
│   ├── index.html          # Docs landing — search, reader-level cards
│   ├── clients.html        # Client guide — jobs, wallet, pricing, API
│   ├── miners.html         # Miner guide — GPU setup, earnings, Ollama
│   ├── developers.html     # Developer guide — SDKs, contributing, bounties
│   ├── full-documentation.html  # Complete technical reference
│   ├── components.html     # Architecture & components overview
│   ├── flowchart.html      # End-to-end system flow diagram
│   ├── api.html            # REST API reference
│   ├── blockchain-node.html
│   ├── coordinator-api.html
│   ├── explorer-web.html
│   ├── marketplace-web.html
│   ├── wallet-daemon.html
│   ├── trade-exchange.html
│   ├── pool-hub.html
│   ├── browser-wallet.html # Redirect → /wallet/
│   ├── css/docs.css        # Shared stylesheet (1,870 lines)
│   └── js/theme.js         # Dark/light theme toggle
└── wallet/
    └── index.html          # Browser wallet landing page
```

## Deployment

Deployed in the AITBC Incus container:

| | |
|---|---|
| **Container IP** | 10.1.223.93 |
| **Domain** | aitbc.bubuit.net |
| **Docs** | aitbc.bubuit.net/docs/ |

### Push to live

```bash
# Push all files via SSH
scp /home/oib/windsurf/aitbc/website/index.html /home/oib/windsurf/aitbc/website/404.html /home/oib/windsurf/aitbc/website/favicon.svg /home/oib/windsurf/aitbc/website/font-awesome-local.css aitbc-cascade:/var/www/html/
scp /home/oib/windsurf/aitbc/website/docs/*.html aitbc-cascade:/var/www/html/docs/
scp /home/oib/windsurf/aitbc/website/docs/css/docs.css aitbc-cascade:/var/www/html/docs/css/
scp /home/oib/windsurf/aitbc/website/docs/js/theme.js aitbc-cascade:/var/www/html/docs/js/
scp /home/oib/windsurf/aitbc/website/wallet/index.html aitbc-cascade:/var/www/html/wallet/
```

## Key Features

- **Unified header/nav** across all 15 doc pages with theme toggle
- **Live search** on docs index (client-side, 15-page index)
- **Shared CSS** — zero inline `<style>` blocks, one `docs.css`
- **Shared JS** — theme persistence via `theme.js`
- **Zero dead links** — all `href="#"` replaced with real targets
- **Font Awesome 6** consistently across all pages
- **Dark/light mode** with localStorage persistence
