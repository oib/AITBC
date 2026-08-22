# Trade Exchange - AITBC Documentation

Ethereum-to-AITBC exchange with QR payments, user management, and real-time trading. Buy tokens with ETH instantly.

● Live

[Launch Exchange →](https://aitbc.bubuit.net/Exchange/)

## Overview

The AITBC Trade Exchange is a crypto-only platform that enables users to exchange Ethereum for the network tokens. It features a modern, responsive interface with user authentication, wallet management, and real-time trading capabilities.

### Key Features

- Ethereum on-ramp integration with QR code payments
- User management with wallet-based authentication
- Real-time payment monitoring and confirmation
- Individual user wallets and balance tracking
- Transaction history and receipt management
- Mobile-responsive design

## How It Works

The Trade Exchange provides a simple, secure way to acquire the network tokens using Ethereum.

#### 1. Connect Wallet

Click "Connect Wallet" to generate a unique wallet address and create your account

#### 2. Select Amount

Enter the amount of AITBC you want to buy or Ethereum you want to spend

#### 3. Make Payment

Scan the QR code or send Ethereum to the provided address

#### 4. Receive Tokens

the network tokens are credited to your wallet after confirmation

## User Management

The exchange uses a wallet-based authentication system that requires no passwords.

### Authentication Flow

- Users connect with a wallet address (auto-generated for demo)
- System creates or retrieves user account
- Session token issued for secure API access
- 24-hour automatic session expiry

### User Features

- Unique username and user ID
- Personal the wallet with balance tracking
- Complete transaction history
- Secure logout functionality

## Exchange API

The exchange provides RESTful APIs for user management and payment processing.

### User Management Endpoints

`POST /api/users/login`
Login or register with wallet address

`GET /api/users/me`
Get current user profile

`GET /api/users/{id}/balance`
Get user wallet balance

`POST /api/users/logout`
Logout and invalidate session

### Exchange Endpoints

`POST /api/exchange/create-payment`
Create Ethereum deposit request

`GET /api/exchange/payment-status/{id}`
Check payment confirmation status

`GET /api/exchange/rates`
Get current exchange rates

## Security Features

The exchange implements multiple security measures to protect user funds and data.

### Authentication Security

- SHA-256 hashed session tokens
- 24-hour automatic session expiry
- Server-side session validation
- Secure token invalidation on logout

### Payment Security

- Unique payment addresses for each transaction
- Real-time blockchain monitoring
- Payment confirmation requirements (1 confirmation)
- Automatic refund for expired payments

### Privacy

- No personal data collection
- User data isolation
- GDPR compliant design

## Configuration

The exchange can be configured for different environments and requirements.

### Exchange Settings

```bash
# Exchange Rate
ETH_TO_AITBC_RATE=100000

# Payment Settings
MIN_CONFIRMATIONS=1
PAYMENT_TIMEOUT=3600  # 1 hour
MIN_PAYMENT=0.0001  # ETH
MAX_PAYMENT=10      # ETH

# Ethereum Network
ETHEREUM_NETWORK=testnet
ETHEREUM_RPC_URL=http://localhost:8332
ETHEREUM_RPC_USER=user
ETHEREUM_RPC_PASS=password
```

## Getting Started

Start using the Trade Exchange in just a few simple steps.

### 1. Access the Exchange

Visit: [https://aitbc.bubuit.net/Exchange/](https://aitbc.bubuit.net/Exchange/)

### 2. Connect Your Wallet

Click the "Connect Wallet" button. A unique wallet address will be generated for you.

### 3. Get Testnet Ethereum

For testing, get free testnet Ethereum from:
[sepoliafaucet.com](https://sepoliafaucet.com/)

### 4. Make Your First Purchase

1. Enter the amount of AITBC you want to buy
2. Scan the QR code with your Ethereum wallet
3. Wait for confirmation (usually 10-20 minutes on testnet)
4. Receive the network tokens in your wallet

## API Examples

### Create Payment Request

```bash
curl -X POST https://aitbc.bubuit.net/api/exchange/create-payment \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: your-session-token" \
  -d '{
    "aitbc_amount": 1000,
    "eth_amount": 0.01
  }'
```

Response:

```json
{
  "payment_id": "pay_123456",
  "eth_address": "0x0000...",
  "eth_amount": 0.01,
  "qr_code": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "expires_at": "2025-01-29T15:50:00Z"
}
```

### Check Payment Status

```bash
curl -X GET https://aitbc.bubuit.net/api/exchange/payment-status/pay_123456 \
  -H "X-Session-Token: your-session-token"
```

Response:

```json
{
  "payment_id": "pay_123456",
  "status": "confirmed",
  "confirmations": 1,
  "aitbc_amount": 1000,
  "credited_at": "2025-01-29T14:50:00Z"
}
```

## Integration Guide

### Frontend Integration

```javascript
// Connect wallet
async function connectWallet() {
  const response = await fetch('/api/users/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ wallet_address: generatedAddress })
  });
  const { user, token } = await response.json();
  localStorage.setItem('sessionToken', token);
  return user;
}

// Create payment
async function createPayment(aitbcAmount) {
  const response = await fetch('/api/exchange/create-payment', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Session-Token': localStorage.getItem('sessionToken')
    },
    body: JSON.stringify({ aitbc_amount: aitbcAmount })
  });
  return response.json();
}
```

### Backend Integration

```python
# Python example using requests
import requests

class AITBCExchange:
    def __init__(self, base_url="https://aitbc.bubuit.net"):
        self.base_url = base_url
        self.session_token = None

    def login(self, wallet_address):
        response = requests.post(
            f"{self.base_url}/api/users/login",
            json={"wallet_address": wallet_address}
        )
        data = response.json()
        self.session_token = data["token"]
        return data["user"]

    def create_payment(self, aitbc_amount):
        headers = {"X-Session-Token": self.session_token}
        response = requests.post(
            f"{self.base_url}/api/exchange/create-payment",
            json={"aitbc_amount": aitbc_amount},
            headers=headers
        )
        return response.json()
```

## Troubleshooting

### Common Issues

1. **Payment not detected**
   - Verify the transaction was broadcast to the network
   - Check if the payment address is correct
   - Wait for at least 1 confirmation

2. **Session expired**
   - Click "Connect Wallet" to create a new session
   - Sessions automatically expire after 24 hours

3. **QR code not working**
   - Ensure your Ethereum wallet supports QR codes
   - Manually copy the address if needed
   - Check for sufficient wallet balance

### Support

- Check transaction on [block explorer](https://sepolia.etherscan.io)
- Contact support: [aitbc@bubuit.net](mailto:aitbc@bubuit.net)
- Discord: [#exchange-support](https://discord.gg/aitbc)

## Rate Limits

To ensure fair usage, the exchange implements rate limiting:

- 10 payments per hour per user
- 100 API requests per minute per session
- Maximum payment: 10 ETH per transaction

## Future Updates

Planned features for the Trade Exchange:

- Support for additional cryptocurrencies (ETH, USDT)
- Advanced order types (limit orders)
- Trading API for programmatic access
- Mobile app support
- Lightning Network integration

---

**Start trading now at [aitbc.bubuit.net/Exchange/](https://aitbc.bubuit.net/Exchange/)**
