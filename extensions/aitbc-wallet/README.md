# AITBC Browser Wallet Extension

A browser extension that provides AITBC wallet functionality for interacting with the AITBC Trade Exchange and other dApps.

## Features

- **Wallet Management**: Create new accounts or import existing private keys
- **Secure Storage**: Private keys are stored locally in the browser
- **dApp Integration**: Connect to AITBC Trade Exchange and other supported dApps
- **Transaction Signing**: Sign transactions and messages securely
- **Balance Tracking**: View your AITBC token balance

## Installation

### Development Installation

1. Clone this repository
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable "Developer mode" in the top right
4. Click "Load unpacked"
5. Select the `aitbc-wallet` folder

### Production Installation

The extension will be published to the Chrome Web Store. Installation instructions will be available once published.

## Usage

### Connecting to the Exchange

1. Install the AITBC Wallet extension
2. Navigate to https://aitbc.bubuit.net/Exchange
3. Toggle the switch from "Demo Mode" to "Real Mode"
4. Click "Connect AITBC Wallet"
5. Approve the connection request in the popup

### Managing Accounts

1. Click the AITBC Wallet icon in your browser toolbar
2. Use "Create New Account" to generate a new wallet
3. Use "Import Private Key" to restore an existing wallet
4. **Important**: Save your private key securely! It cannot be recovered if lost.

## API Reference

The extension injects a `window.aitbcWallet` object into supported dApps with the following methods:

### `aitbcWallet.connect()`
Connect the dApp to the wallet.
```javascript
const response = await aitbcWallet.connect();
console.log(response.address); // User's AITBC address
```

### `aitbcWallet.getAccount()`
Get the current account address.
```javascript
const address = await aitbcWallet.getAccount();
```

### `aitbcWallet.getBalance(address)`
Get the AITBC balance for an address.
```javascript
const balance = await aitbcWallet.getBalance('aitbc1...');
console.log(balance.amount); // Balance in AITBC
```

### `aitbcWallet.sendTransaction(to, amount, data)`
Send AITBC tokens to another address.
```javascript
const tx = await aitbcWallet.sendTransaction('aitbc1...', 100);
console.log(tx.hash); // Transaction hash
```

### `aitbcWallet.signMessage(message)`
Sign a message with the private key.
```javascript
const signature = await aitbcWallet.signMessage('Hello AITBC!');
```

## Security Considerations

- Private keys are stored locally in Chrome's storage
- Always verify you're on the correct domain before connecting
- Never share your private key with anyone
- Keep your browser and extension updated

## Development

To modify the extension:

1. Make changes to the source files
2. Go to `chrome://extensions/`
3. Click the refresh button on the AITBC Wallet card
4. Test your changes

## File Structure

```
aitbc-wallet/
├── manifest.json      # Extension configuration
├── content.js         # Content script for dApp communication
├── injected.js        # Script injected into dApps
├── popup.html         # Extension popup UI
├── popup.js           # Popup logic
├── icons/             # Extension icons
└── README.md          # This file
```

## Support

For issues or feature requests, please create an issue in the repository.
