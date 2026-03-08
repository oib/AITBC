# AITBC Browser Wallet Extensions

This directory contains browser wallet extensions for AITBC, supporting both Chrome and Firefox browsers.

## Quick Start

### For Chrome/Brave/Edge Users

1. Navigate to `aitbc-wallet/` folder
2. Follow the installation instructions in `aitbc-wallet/README.md`

### For Firefox Users

1. Navigate to `aitbc-wallet-firefox/` folder
2. Follow the installation instructions in `aitbc-wallet-firefox/README.md`

## Using the Extensions

1. Install the appropriate extension for your browser
2. Navigate to the AITBC Trade Exchange: https://aitbc.bubuit.net/Exchange
3. Toggle from "Demo Mode" to "Real Mode"
4. Click "Connect AITBC Wallet"
5. Create a new account or import an existing one
6. Approve the connection request

## Features

- ✅ Cross-browser support (Chrome, Firefox, Edge, Brave)
- ✅ Secure local key storage
- ✅ dApp connection management
- ✅ Transaction signing
- ✅ Message signing
- ✅ Balance tracking
- ✅ Account management (create/import)

## Security Best Practices

1. **Never share your private key** - It's the key to your funds
2. **Keep backups** - Save your private key in a secure location
3. **Verify URLs** - Always check you're on aitbc.bubuit.net
4. **Use strong passwords** - Protect your browser with a strong password
5. **Keep updated** - Keep your browser and extension updated

## Development

Both extensions share most of their code:

- `injected.js` - Provides the wallet API to dApps
- `popup.html/js` - Wallet user interface
- `content.js` - Communicates between the extension and dApps

The main differences are:
- Chrome uses Manifest V3
- Firefox uses Manifest V2 (required for full functionality)
- Different background script architectures

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   dApp Page     │────▶│  Content Script  │────▶│ Background Script│
│ (Exchange UI)   │     │ (bridge)         │     │ (wallet logic)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                ▲                        │
                                │                        ▼
                       ┌──────────────────┐     ┌─────────────────┐
                       │  Injected Script │     │   Extension UI  │
                       │ (window.aitbcWallet)│   │ (popup.html)   │
                       └──────────────────┘     └─────────────────┘
```

## Support

For issues or questions:
1. Check the individual README files for your browser
2. Create an issue in the repository
3. Join our community discussions
