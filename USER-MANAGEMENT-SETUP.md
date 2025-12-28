# User Management System for AITBC Trade Exchange

## Overview
The AITBC Trade Exchange now includes a complete user management system that allows individual users to have their own wallets, balances, and transaction history. Each user is identified by their wallet address and has a unique session for secure operations.

## Features Implemented

### 1. User Registration & Login
- **Wallet-based Authentication**: Users connect with their wallet address
- **Auto-registration**: New wallets automatically create a user account
- **Session Management**: Secure token-based sessions (24-hour expiry)
- **User Profiles**: Each user has a unique ID, email, and username

### 2. Wallet Management
- **Individual Wallets**: Each user gets their own AITBC wallet
- **Balance Tracking**: Real-time balance updates
- **Address Generation**: Unique wallet addresses for each user

### 3. Transaction History
- **Personal Transactions**: Each user sees only their own transactions
- **Transaction Types**: Buy, sell, deposit, withdrawal tracking
- **Status Updates**: Real-time transaction status

## API Endpoints

### User Authentication
```http
POST /api/users/login
{
    "wallet_address": "aitbc1abc123..."
}
```

Response:
```json
{
    "user_id": "uuid",
    "email": "wallet@aitbc.local",
    "username": "user_abc123",
    "created_at": "2025-12-28T...",
    "session_token": "sha256_token"
}
```

### User Profile
```http
GET /api/users/me
Headers: X-Session-Token: <token>
```

### User Balance
```http
GET /api/users/{user_id}/balance
Headers: X-Session-Token: <token>
```

Response:
```json
{
    "user_id": "uuid",
    "address": "aitbc_uuid123",
    "balance": 1000.0,
    "updated_at": "2025-12-28T..."
}
```

### Transaction History
```http
GET /api/users/{user_id}/transactions
Headers: X-Session-Token: <token>
```

### Logout
```http
POST /api/users/logout
Headers: X-Session-Token: <token>
```

## Frontend Implementation

### 1. Connect Wallet Flow
1. User clicks "Connect Wallet"
2. Generates a demo wallet address
3. Calls `/api/users/login` with wallet address
4. Receives session token and user data
5. Updates UI with user info

### 2. UI Components
- **Wallet Section**: Shows address, username, balance
- **Connect Button**: Visible when not logged in
- **Logout Button**: Clears session and resets UI
- **Balance Display**: Real-time AITBC balance

### 3. Session Management
- Session token stored in JavaScript variable
- Token sent with all API requests
- Automatic logout on token expiry
- Manual logout option

## Database Schema

### Users Table
- `id`: UUID (Primary Key)
- `email`: Unique string
- `username`: Unique string
- `status`: active/inactive/suspended
- `created_at`: Timestamp
- `last_login`: Timestamp

### Wallets Table
- `id`: Integer (Primary Key)
- `user_id`: UUID (Foreign Key)
- `address`: Unique string
- `balance`: Float
- `created_at`: Timestamp
- `updated_at`: Timestamp

### Transactions Table
- `id`: UUID (Primary Key)
- `user_id`: UUID (Foreign Key)
- `wallet_id`: Integer (Foreign Key)
- `type`: deposit/withdrawal/purchase/etc.
- `status`: pending/completed/failed
- `amount`: Float
- `fee`: Float
- `created_at`: Timestamp
- `confirmed_at`: Timestamp

## Security Features

### 1. Session Security
- SHA-256 hashed tokens
- 24-hour automatic expiry
- Server-side session validation
- Secure token invalidation on logout

### 2. API Security
- Session token required for protected endpoints
- User isolation (users can only access their own data)
- Input validation and sanitization

### 3. Future Enhancements
- JWT tokens for better scalability
- Multi-factor authentication
- Biometric wallet support
- Hardware wallet integration

## How It Works

### 1. First Time User
1. User connects wallet
2. System creates new user account
3. Wallet is created and linked to user
4. Session token issued
5. User can start trading

### 2. Returning User
1. User connects wallet
2. System finds existing user
3. Updates last login
4. Issues new session token
5. User sees their balance and history

### 3. Trading
1. User initiates purchase
2. Payment request created with user_id
3. Bitcoin payment processed
4. AITBC credited to user's wallet
5. Transaction recorded

## Testing

### Test Users
Each wallet connection creates a unique user:
- Address: `aitbc1wallet_[random]x...`
- Email: `wallet@aitbc.local`
- Username: `user_[last_8_chars]`

### Demo Mode
- No real registration required
- Instant wallet creation
- Testnet Bitcoin support
- Simulated balance updates

## Next Steps

### 1. Enhanced Features
- Email verification
- Password recovery
- 2FA authentication
- Profile customization

### 2. Advanced Trading
- Limit orders
- Stop-loss
- Trading history analytics
- Portfolio tracking

### 3. Integration
- MetaMask support
- WalletConnect protocol
- Hardware wallets (Ledger, Trezor)
- Mobile wallet apps

## Support

For issues or questions:
- Check the logs: `journalctl -u aitbc-coordinator -f`
- API endpoints: `https://aitbc.bubuit.net/api/docs`
- Trade Exchange: `https://aitbc.bubuit.net/Exchange`
