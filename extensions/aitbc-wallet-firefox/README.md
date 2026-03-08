# AITBC Wallet Extension for Firefox

A Firefox browser extension that provides AITBC wallet functionality for interacting with the AITBC Trade Exchange and other dApps.

## Differences from Chrome Version

This version is specifically built for Firefox with the following differences:

- Uses Manifest V2 (Firefox still requires V2 for full functionality)
- Uses `browser_action` instead of `action` (V2 syntax)
- Uses `chrome.runtime.connect()` for background script communication
- Background script uses persistent connections via ports

## Installation

### Development Installation

1. Clone this repository
2. Open Firefox and navigate to `about:debugging`
3. Click "This Firefox" in the left sidebar
4. Click "Load Temporary Add-on..."
5. Select the `manifest.json` file from the `aitbc-wallet-firefox` folder

### Production Installation

The extension will be published to the Firefox Add-on Store (AMO). Installation instructions will be available once published.

## Usage

The usage is identical to the Chrome version:

1. Install the AITBC Wallet extension
2. Navigate to https://aitbc.bubuit.net/Exchange
3. Toggle the switch from "Demo Mode" to "Real Mode"
4. Click "Connect AITBC Wallet"
5. Approve the connection request in the popup

## Features

- **Wallet Management**: Create new accounts or import existing private keys
- **Secure Storage**: Private keys are stored locally in Firefox's storage
- **dApp Integration**: Connect to AITBC Trade Exchange and other supported dApps
- **Transaction Signing**: Sign transactions and messages securely
- **Balance Tracking**: View your AITBC token balance

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

- Private keys are stored locally in Firefox's storage
- Always verify you're on the correct domain before connecting
- Never share your private key with anyone
- Keep your browser and extension updated

## Development

To modify the extension:

1. Make changes to the source files
2. Go to `about:debugging` in Firefox
3. Find "AITBC Wallet" and click "Reload"
4. Test your changes

## File Structure

```
aitbc-wallet-firefox/
├── manifest.json      # Extension configuration (Manifest V2)
├── background.js       # Background script for wallet operations
├── content.js         # Content script for dApp communication
├── injected.js        # Script injected into dApps
├── popup.html         # Extension popup UI
├── popup.js           # Popup logic
├── icons/             # Extension icons
└── README.md          # This file
```

## Firefox-Specific Notes

- Firefox requires Manifest V2 for extensions that use content scripts in this manner
- The `browser_action` API is used instead of the newer `action` API
- Background scripts use port-based communication for better performance
- Storage APIs use `chrome.storage` which is compatible with Firefox

## Troubleshooting

### Extension not loading
- Ensure you're loading the `manifest.json` file, not the folder
- Check the Browser Console for error messages (`Ctrl+Shift+J`)

### dApp connection not working
- Refresh the dApp page after installing/updating the extension
- Check that the site is in the `matches` pattern in manifest.json
- Look for errors in the Browser Console

### Permission errors
- Firefox may show additional permission prompts
- Make sure to allow all requested permissions when installing
