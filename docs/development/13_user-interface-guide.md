# AITBC Trade Exchange - User Interface Guide

## Overview
The AITBC Trade Exchange features a modern, intuitive interface with user authentication, wallet management, and trading capabilities.

## Navigation

### Main Menu
Located in the top header, you'll find:
- **Trade**: Buy and sell AITBC tokens
- **Marketplace**: Browse GPU computing offers
- **Wallet**: View your profile and wallet information

### User Status
- **Not Connected**: Shows "Connect Wallet" button
- **Connected**: Shows your username with profile and logout icons

## Getting Started

### 1. Connect Your Wallet
1. Click the "Connect Wallet" button in the navigation bar
2. A demo wallet will be automatically created for you
3. Your user profile will be displayed with:
   - Unique username (format: `user_[random]`)
   - User ID (UUID)
   - Member since date

### 2. View Your Profile
Click on "Wallet" in the navigation to see:
- **User Profile Card**: Your account information
- **AITBC Wallet**: Your wallet address and balance
- **Transaction History**: Your trading activity

## Trading AITBC

### Buy AITBC with Bitcoin
1. Navigate to the **Trade** section
2. Enter the amount of AITBC you want to buy
3. The system calculates the equivalent Bitcoin amount
4. Click "Create Payment Request"
5. A QR code and payment address will be displayed
6. Send Bitcoin to the provided address
7. Wait for confirmation (1 confirmation needed)
8. AITBC tokens will be credited to your wallet

### Exchange Rates
- **Current Rate**: 1 BTC = 100,000 AITBC
- **Fee**: 0.5% transaction fee
- **Updates**: Prices refresh every 30 seconds

## Wallet Features

### User Profile
- **Username**: Auto-generated unique identifier
- **User ID**: Your unique UUID in the system
- **Member Since**: When you joined the platform
- **Logout**: Securely disconnect from the exchange

### AITBC Wallet
- **Address**: Your unique AITBC wallet address
- **Balance**: Current AITBC token balance
- **USD Value**: Approximate value in USD

### Transaction History
- **Date/Time**: When transactions occurred
- **Type**: Buy, sell, deposit, withdrawal
- **Amount**: Quantity of AITBC tokens
- **Status**: Pending, completed, or failed

## Security Features

### Session Management
- **Token-based Authentication**: Secure session tokens
- **24-hour Expiry**: Automatic session timeout
- **Logout**: Manual session termination

### Privacy
- **Individual Accounts**: Each user has isolated data
- **Secure API**: All requests require authentication
- **No Passwords**: Wallet-based authentication

## Tips for Users

### First Time
1. Click "Connect Wallet" to create your account
2. Your wallet and profile are created automatically
3. No registration or password needed

### Trading
1. Always check the current exchange rate
2. Bitcoin payments require 1 confirmation
3. AITBC tokens are credited automatically

### Security
1. Logout when done trading
2. Your session expires after 24 hours
3. Each wallet connection creates a new session

## Demo Features

### Test Mode
- **Testnet Bitcoin**: Uses Bitcoin testnet for safe testing
- **Demo Wallets**: Auto-generated wallet addresses
- **Simulated Trading**: No real money required

### Getting Testnet Bitcoin
1. Visit a testnet faucet (e.g., https://testnet-faucet.mempool.co/)
2. Enter your testnet address
3. Receive free testnet Bitcoin for testing

## Troubleshooting

### Connection Issues
- Refresh the page and try connecting again
- Check your internet connection
- Ensure JavaScript is enabled

### Balance Not Showing
- Try refreshing the page
- Check if you're logged in
- Contact support if issues persist

### Payment Problems
- Ensure you send the exact amount
- Wait for at least 1 confirmation
- Check the transaction status on the blockchain

## Support

For help or questions:
- **API Docs**: https://aitbc.bubuit.net/api/docs
- **Admin Panel**: https://aitbc.bubuit.net/admin/stats
- **Platform**: https://aitbc.bubuit.net/Exchange

## Keyboard Shortcuts

- **Ctrl+K**: Quick navigation (coming soon)
- **Esc**: Close modals
- **Enter**: Confirm actions

## Browser Compatibility

Works best with modern browsers:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Mobile Support

- Responsive design for tablets and phones
- Touch-friendly interface
- Mobile wallet support (coming soon)
