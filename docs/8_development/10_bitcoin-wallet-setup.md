# Bitcoin Wallet Integration for AITBC Trade Exchange

## Overview
The AITBC Trade Exchange now supports Bitcoin payments for purchasing AITBC tokens. Users can send Bitcoin to a generated address and receive AITBC tokens after confirmation.

## Current Implementation

### Frontend Features
- **Payment Request Generation**: Users enter the amount of AITBC they want to buy
- **Dynamic QR Code**: A QR code is generated with the Bitcoin address and amount
- **Payment Monitoring**: The system automatically checks for payment confirmation
- **Real-time Updates**: Users see payment status updates in real-time

### Backend Features
- **Payment API**: `/api/exchange/create-payment` creates payment requests
- **Status Tracking**: `/api/exchange/payment-status/{id}` checks payment status
- **Exchange Rates**: `/api/exchange/rates` provides current BTC/AITBC rates

## Configuration

### Bitcoin Settings
```python
BITCOIN_CONFIG = {
    'testnet': True,                    # Using Bitcoin testnet
    'main_address': 'tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh',
    'exchange_rate': 100000,           # 1 BTC = 100,000 AITBC
    'min_confirmations': 1,
    'payment_timeout': 3600            # 1 hour expiry
}
```

### Environment Variables
```bash
BITCOIN_TESTNET=true
BITCOIN_ADDRESS=tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh
BITCOIN_PRIVATE_KEY=your_private_key
BLOCKCHAIN_API_KEY=your_blockchain_api_key
WEBHOOK_SECRET=your_webhook_secret
MIN_CONFIRMATIONS=1
BTC_TO_AITBC_RATE=100000
```

## How It Works

1. **User Initiates Purchase**
   - Enters AITBC amount or BTC amount
   - System calculates the conversion
   - Creates a payment request

2. **Payment Address Generated**
   - Unique payment address (demo: uses fixed address)
   - QR code generated with `bitcoin:` URI
   - Payment details displayed

3. **Payment Monitoring**
   - System checks blockchain every 30 seconds
   - Updates payment status automatically
   - Notifies user when confirmed

4. **Token Minting**
   - Upon confirmation, AITBC tokens are minted
   - Tokens credited to user's wallet
   - Transaction recorded

## Security Considerations

### Current (Demo) Implementation
- Uses a fixed Bitcoin testnet address
- No private key integration
- Manual payment confirmation for demo

### Production Requirements
- HD wallet for unique address generation
- Blockchain API integration (Blockstream, BlockCypher, etc.)
- Webhook signatures for payment notifications
- Multi-signature wallet support
- Cold storage for funds

## API Endpoints

### Create Payment Request
```http
POST /api/exchange/create-payment
{
    "user_id": "user_wallet_address",
    "aitbc_amount": 1000,
    "btc_amount": 0.01
}
```

### Check Payment Status
```http
GET /api/exchange/payment-status/{payment_id}
```

### Get Exchange Rates
```http
GET /api/exchange/rates
```

## Testing

### Testnet Bitcoin
- Use Bitcoin testnet for testing
- Get testnet Bitcoin from faucets:
  - https://testnet-faucet.mempool.co/
  - https://coinfaucet.eu/en/btc-testnet/

### Demo Mode
- Currently running in demo mode
- Payments are simulated
- Use admin API to manually confirm payments

## Next Steps

1. **Production Wallet Integration**
   - Implement HD wallet (BIP32/BIP44)
   - Connect to mainnet/testnet
   - Secure private key storage

2. **Blockchain API Integration**
   - Real-time transaction monitoring
   - Webhook implementation
   - Confirmation tracking

3. **Enhanced Security**
   - Multi-signature support
   - Cold storage integration
   - Audit logging

4. **User Experience**
   - Payment history
   - Refund mechanism
   - Email notifications

## Support

For issues or questions:
- Check the logs: `journalctl -u aitbc-coordinator -f`
- API documentation: `https://aitbc.bubuit.net/api/docs`
- Admin panel: `https://aitbc.bubuit.net/admin/stats`
