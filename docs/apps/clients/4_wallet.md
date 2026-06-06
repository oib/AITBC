# Wallet Management

Manage your AITBC wallet and tokens.

## Create Wallet

```bash
aitbc wallet create --name my-wallet
```

Save the seed phrase securely!

## Import Wallet

```bash
aitbc wallet import --seed "your seed phrase words"
```

## View Balance

```bash
aitbc wallet balance
```

### Detailed Balance

```bash
aitbc wallet balance --detailed
```

Shows:
- Available balance
- Pending transactions
- Locked tokens

## Send Tokens

```bash
aitbc wallet send --to <ADDRESS> --amount 100
```

### With Memo

```bash
aitbc wallet send --to <ADDRESS> --amount 100 --memo "Payment for job"
```

## Transaction History

```bash
aitbc wallet history
```

### Filter

```bash
aitbc wallet history --type sent
aitbc wallet history --type received
```

## Security

### Backup Wallet

```bash
aitbc wallet export --output wallet.json
```

### Change Password

```bash
aitbc wallet change-password
```

## Next

- [5_pricing-billing.md](./5_pricing-billing.md) — Cost structure and invoices
- [CLI Guide](../0_getting_started/3_cli.md) — Full CLI reference
