# Ethereum Wallet Integration for AITBC Trade Exchange

## Overview

The AITBC Trade Exchange now supports Ethereum deposits for purchasing the network tokens. Users can send Ethereum to a generated address and receive the network tokens after confirmation.

## Current Implementation

### Frontend Features

- **Payment Request Generation**: Users enter the amount of AITBC they want to buy
- **Dynamic QR Code**: A QR code is generated with the Ethereum address and amount
- **Payment Monitoring**: The system automatically checks for payment confirmation
- **Real-time Updates**: Users see payment status updates in real-time

### Backend Features

- **Payment API**: `/v1/exchange/create-payment` creates payment requests
- **Status Tracking**: `/v1/exchange/payment-status/{id}` checks payment status
- **Exchange Rates**: `/v1/exchange/rates` provides current ETH/AITBC rates

## Configuration

### Ethereum Settings

```python
# apps/coordinator-api/.../infrastructure/routers/exchange.py — the live
# config is a module-level dict, not environment variables:
ETH_CONFIG = {
    "testnet": True,
    "main_address": "0x0000000000000000000000000000000000000000",  # placeholder
    "exchange_rate": 1000,     # 1 ETH = 1,000 AITBC
    "min_confirmations": 12,
    "payment_timeout": 3600,   # 1 hour expiry
}
```

### Environment Variables

> **No ETH exchange env vars exist.** `ETHEREUM_TESTNET`, `ETHEREUM_ADDRESS`,
> `ETHEREUM_PRIVATE_KEY`, `BLOCKCHAIN_API_KEY`, `WEBHOOK_SECRET`,
> `MIN_CONFIRMATIONS`, and `ETH_TO_AITBC_RATE` were documented historically
> but no code reads them — `ETH_CONFIG` above is hardcoded in the router.
> The standalone exchange service's real env vars are `BRIDGE_FEE_RATE`,
> `BRIDGE_ETH_ADDRESS`, `MIN_ETH_DEPOSIT`, `ETH_NETWORK`,
> `EXCHANGE_WEBHOOK_SECRET`, and `EXCHANGE_API_KEY`.

## How It Works

1. **User Initiates Purchase**
   - Enters AITBC amount or ETH amount
   - System calculates the conversion
   - Creates a payment request

2. **Payment Address Generated**
   - Unique payment address (demo: uses fixed address)
   - QR code generated with `ethereum:` URI
   - Payment details displayed

3. **Payment Monitoring**
   - System checks blockchain every 30 seconds
   - Updates payment status automatically
   - Notifies user when confirmed

4. **Token Minting**
   - Upon confirmation, the network tokens are minted
   - Tokens credited to user's wallet
   - Transaction recorded

## Security Considerations

### Current (Demo) Implementation

- Uses a fixed Ethereum testnet address
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
POST /v1/exchange/create-payment
{
    "user_id": "user_wallet_address",
    "aitbc_amount": 1000,
    "eth_amount": 0.01
}
```

### Check Payment Status

```http
GET /v1/exchange/payment-status/{payment_id}
```

### Get Exchange Rates

```http
GET /v1/exchange/rates
```

Also mounted on coordinator-api (`:8203`): `POST /v1/exchange/confirm-payment/{payment_id}` and `GET /v1/exchange/market-stats`.

## Testing

### Testnet Ethereum

- Use Ethereum testnet for testing
- Get testnet Ethereum from a faucet:
  - https://sepoliafaucet.com/

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

- Check the logs: `journalctl -u aitbc-coordinator-api -f`
- API documentation: `http://<host>:8203/docs` (FastAPI Swagger UI on coordinator-api)
