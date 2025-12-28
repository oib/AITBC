# Trade Exchange Documentation

## Overview

The AITBC Trade Exchange is a web platform that allows users to buy AITBC tokens using Bitcoin. It features a modern, responsive interface with user authentication, wallet management, and real-time trading capabilities.

## Features

### Bitcoin Wallet Integration
- **Payment Gateway**: Buy AITBC tokens with Bitcoin
- **QR Code Support**: Mobile-friendly payment QR codes
- **Real-time Monitoring**: Automatic payment confirmation tracking
- **Exchange Rate**: 1 BTC = 100,000 AITBC (configurable)

### User Management
- **Wallet-based Authentication**: No passwords required
- **Individual Accounts**: Each user has a unique wallet and balance
- **Session Security**: 24-hour token-based sessions
- **Profile Management**: View transaction history and account details

### Trading Interface
- **Live Prices**: Real-time exchange rate updates
- **Payment Tracking**: Monitor Bitcoin payments and AITBC credits
- **Transaction History**: Complete record of all trades
- **Mobile Responsive**: Works on all devices

## Getting Started

### 1. Access the Exchange
Visit: https://aitbc.bubuit.net/Exchange/

### 2. Connect Your Wallet
1. Click "Connect Wallet" in the navigation
2. A unique wallet address is generated
3. Your user account is created automatically

### 3. Buy AITBC Tokens
1. Navigate to the Trade section
2. Enter the amount of AITBC you want to buy
3. The Bitcoin equivalent is calculated
4. Click "Create Payment Request"
5. Send Bitcoin to the provided address
6. Wait for confirmation (1 confirmation needed)
7. AITBC tokens are credited to your wallet

## API Reference

### User Management

#### Login/Register
```http
POST /api/users/login
{
    "wallet_address": "aitbc1abc123..."
}
```

Canonical route (same backend, without compatibility proxy):
```http
POST /api/v1/users/login
{
    "wallet_address": "aitbc1abc123..."
}
```

#### Get User Profile
```http
GET /api/users/me
Headers: X-Session-Token: <token>
```

Canonical route:
```http
GET /api/v1/users/users/me
Headers: X-Session-Token: <token>
```

#### Get User Balance
```http
GET /api/users/{user_id}/balance
Headers: X-Session-Token: <token>
```

Canonical route:
```http
GET /api/v1/users/users/{user_id}/balance
Headers: X-Session-Token: <token>
```

#### Logout
```http
POST /api/users/logout
Headers: X-Session-Token: <token>
```

Canonical route:
```http
POST /api/v1/users/logout
Headers: X-Session-Token: <token>
```

### Exchange Operations

#### Create Payment Request
```http
POST /api/exchange/create-payment
{
    "user_id": "uuid",
    "aitbc_amount": 1000,
    "btc_amount": 0.01
}
Headers: X-Session-Token: <token>
```

#### Check Payment Status
```http
GET /api/exchange/payment-status/{payment_id}
```

#### Get Exchange Rates
```http
GET /api/exchange/rates
```

## Configuration

### Bitcoin Settings
- **Network**: Bitcoin Testnet (for demo)
- **Confirmations Required**: 1
- **Payment Timeout**: 1 hour
- **Main Address**: tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh

### Exchange Settings
- **Rate**: 1 BTC = 100,000 AITBC
- **Fee**: 0.5% transaction fee
- **Min Payment**: 0.0001 BTC
- **Max Payment**: 10 BTC

## Security

### Authentication
- **Session Tokens**: SHA-256 hashed tokens
- **Expiry**: 24 hours automatic timeout
- **Storage**: Server-side session management

### Privacy
- **User Isolation**: Each user has private data
- **No Tracking**: No personal data collected
- **GDPR Compliant**: Minimal data retention

## Development

### Frontend Stack
- **HTML5**: Semantic markup
- **CSS3**: TailwindCSS for styling
- **JavaScript**: Vanilla JS with Axios
- **Lucide Icons**: Modern icon library

### Backend Stack
- **FastAPI**: Python web framework
- **SQLModel**: Database ORM
- **SQLite**: Development database
- **Pydantic**: Data validation

### File Structure
```
apps/trade-exchange/
├── index.html          # Main application
├── bitcoin-wallet.py   # Bitcoin integration
└── README.md          # Setup instructions

apps/coordinator-api/src/app/
├── routers/
│   ├── users.py       # User management
│   └── exchange.py    # Exchange operations
├── domain/
│   └── user.py        # User models
└── schemas.py         # API schemas
```

## Deployment

### Production
- **URL**: https://aitbc.bubuit.net/Exchange/
- **SSL**: Fully configured
- **CDN**: Nginx static serving
- **API**: /api/v1/* endpoints

### Environment Variables
```bash
BITCOIN_TESTNET=true
BITCOIN_ADDRESS=tb1q...
BTC_TO_AITBC_RATE=100000
MIN_CONFIRMATIONS=1
```

## Testing

### Testnet Bitcoin
Get free testnet Bitcoin from:
- https://testnet-faucet.mempool.co/
- https://coinfaucet.eu/en/btc-testnet/

### Demo Mode
- No real Bitcoin required
- Simulated payments for testing
- Auto-generated wallet addresses

## Troubleshooting

### Common Issues

**Payment Not Showing**
- Check transaction has 1 confirmation
- Verify correct amount sent
- Refresh the page

**Can't Connect Wallet**
- Check JavaScript is enabled
- Clear browser cache
- Try a different browser

**Balance Incorrect**
- Wait for blockchain sync
- Check transaction history
- Contact support

### Logs
Check application logs:
```bash
journalctl -u aitbc-coordinator -f
```

## Future Enhancements

### Planned Features
- [ ] MetaMask wallet support
- [ ] Advanced trading charts
- [ ] Limit orders
- [ ] Mobile app
- [ ] Multi-currency support

### Technical Improvements
- [ ] Redis session storage
- [ ] PostgreSQL database
- [ ] Microservices architecture
- [ ] WebSocket real-time updates

## Support

For help or questions:
- **Documentation**: https://aitbc.bubuit.net/docs/
- **API Docs**: https://aitbc.bubuit.net/api/docs
- **Admin Panel**: https://aitbc.bubuit.net/admin/stats

## License

This project is part of the AITBC ecosystem. See the main repository for license information.
