# AITBC-AUDIT-4 — cli/aitbc_cli Audit Findings

## Scope

Reviewed all 89 Python source files under `cli/aitbc_cli` for command groups,
argument parsing, error handling, secret/credential handling, and `Decimal`
usage. No source files were modified.

## Findings

### 1. Float used for monetary amount in multisig validation

- **File:** `cli/aitbc_cli/utils/crypto_utils.py:140`
- **Severity:** High
- **Issue:** `amount = float(tx_data["amount"])` converts a monetary amount to
  binary float, risking rounding in multisig validation.
- **Suggested fix:** Replace with `Decimal`:

  ```python
  from decimal import Decimal
  amount = Decimal(str(tx_data["amount"]))
  ```

### 2. Sensitive island credentials file read without permission validation

- **File:** `cli/aitbc_cli/utils/island_credentials.py:36`
- **Severity:** Medium
- **Issue:** `with open(credentials_path) as f:` loads island RPC credentials
  without checking file owner or mode.
- **Suggested fix:** Reject insecure permissions before `json.load`:

  ```python
  if stat.S_IMODE(credentials_path.stat().st_mode) > 0o600:
      raise PermissionError(
          f"Credentials file has insecure permissions: {credentials_path}"
      )
  ```

### 3. Broad `except Exception` masks non-subprocess errors

- **File:** `cli/aitbc_cli/utils/subprocess.py:31`
- **Severity:** Low
- **Issue:** `except Exception as e:` catches `KeyboardInterrupt` and other
  unexpected errors in subprocess helpers.
- **Suggested fix:** Catch only subprocess-related exceptions:

  ```python
  except (OSError, subprocess.SubprocessError) as e:
  ```

### 4. Command-level exchange amount cast to float

- **File:** `cli/aitbc_cli/commands/exchange_island.py:102`
- **Severity:** High
- **Issue:** `"amount": float(ait_amount)` uses float for an exchange order
  amount.
- **Suggested fix:** Use `Decimal`:

  ```python
  "amount": Decimal(str(ait_amount))
  ```

### 5. Wallet balance model uses `float` instead of `Decimal`

- **File:** `cli/aitbc_cli/utils/wallet_daemon_client.py:54`
- **Severity:** High
- **Issue:** `balance: float` in the `WalletBalance` dataclass stores token
  balances as binary float.
- **Suggested fix:** Change to `Decimal` and parse daemon responses with
  `Decimal(...)`.

## Notes

- All findings are read-only audit observations.
- One non-blocking hardening item was triaged to `DEMO-2` for credential file
  permission hardening.

## Related

- Parent audit: `AITBC-AUDIT-1`
- Evidence comment on `AITBC-AUDIT-1`, 2026-07-31T06:12:05Z
