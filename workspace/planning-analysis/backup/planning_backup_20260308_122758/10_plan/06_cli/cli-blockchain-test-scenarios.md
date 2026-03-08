# CLI Blockchain Commands Test Scenarios

This document outlines the test scenarios for the `aitbc blockchain` command group. These scenarios verify the functionality, argument parsing, and output formatting of blockchain operations and queries.

## 1. `blockchain balance`

**Command Description:** Get the balance of an address across all chains.

### Scenario 1.1: Valid Address Balance
- **Command:** `aitbc blockchain balance --address <valid_address>`
- **Description:** Query the balance of a known valid wallet address.
- **Expected Output:** A formatted display (table or list) showing the token balance on each configured chain.

### Scenario 1.2: Invalid Address Format
- **Command:** `aitbc blockchain balance --address invalid_addr_format`
- **Description:** Query the balance using an improperly formatted address.
- **Expected Output:** An error message indicating that the address format is invalid.

## 2. `blockchain block`

**Command Description:** Get details of a specific block.

### Scenario 2.1: Valid Block Hash
- **Command:** `aitbc blockchain block <valid_block_hash>`
- **Description:** Retrieve detailed information for a known block hash.
- **Expected Output:** Detailed JSON or formatted text displaying block headers, timestamp, height, and transaction hashes.

### Scenario 2.2: Unknown Block Hash
- **Command:** `aitbc blockchain block 0x0000000000000000000000000000000000000000000000000000000000000000`
- **Description:** Attempt to retrieve a non-existent block.
- **Expected Output:** An error message stating the block was not found.

## 3. `blockchain blocks`

**Command Description:** List recent blocks.

### Scenario 3.1: Default Listing
- **Command:** `aitbc blockchain blocks`
- **Description:** List the most recent blocks using default limits.
- **Expected Output:** A table showing the latest blocks, their heights, hashes, and timestamps.

### Scenario 3.2: Custom Limit and Starting Height
- **Command:** `aitbc blockchain blocks --limit 5 --from-height 100`
- **Description:** List exactly 5 blocks starting backwards from block height 100.
- **Expected Output:** A table with exactly 5 blocks, starting from height 100 down to 96.

## 4. `blockchain faucet`

**Command Description:** Mint devnet funds to an address.

### Scenario 4.1: Standard Minting
- **Command:** `aitbc blockchain faucet --address <valid_address> --amount 1000`
- **Description:** Request 1000 tokens from the devnet faucet.
- **Expected Output:** Success message with the transaction hash of the mint operation.

### Scenario 4.2: Exceeding Faucet Limits
- **Command:** `aitbc blockchain faucet --address <valid_address> --amount 1000000000`
- **Description:** Attempt to request an amount larger than the faucet allows.
- **Expected Output:** An error message indicating the requested amount exceeds maximum limits.

## 5. `blockchain genesis`

**Command Description:** Get the genesis block of a chain.

### Scenario 5.1: Retrieve Genesis Block
- **Command:** `aitbc blockchain genesis --chain-id ait-devnet`
- **Description:** Fetch the genesis block details for a specific chain.
- **Expected Output:** Detailed JSON or formatted text of block 0 for the specified chain.

## 6. `blockchain head`

**Command Description:** Get the head (latest) block of a chain.

### Scenario 6.1: Retrieve Head Block
- **Command:** `aitbc blockchain head --chain-id ait-testnet`
- **Description:** Fetch the current highest block for a specific chain.
- **Expected Output:** Details of the latest block on the specified chain.

## 7. `blockchain info`

**Command Description:** Get general blockchain information.

### Scenario 7.1: Network Info
- **Command:** `aitbc blockchain info`
- **Description:** Retrieve general metadata about the network.
- **Expected Output:** Information including network name, version, protocol version, and active chains.

## 8. `blockchain peers`

**Command Description:** List connected peers.

### Scenario 8.1: View Peers
- **Command:** `aitbc blockchain peers`
- **Description:** View the list of currently connected P2P nodes.
- **Expected Output:** A table listing peer IDs, IP addresses, latency, and connection status.

## 9. `blockchain send`

**Command Description:** Send a transaction to a chain.

### Scenario 9.1: Valid Transaction
- **Command:** `aitbc blockchain send --chain-id ait-devnet --from <sender_addr> --to <recipient_addr> --data "payload"`
- **Description:** Submit a standard transaction to a specific chain.
- **Expected Output:** Success message with the resulting transaction hash.

## 10. `blockchain status`

**Command Description:** Get blockchain node status.

### Scenario 10.1: Default Node Status
- **Command:** `aitbc blockchain status`
- **Description:** Check the status of the primary connected node.
- **Expected Output:** Operational status, uptime, current block height, and memory usage.

### Scenario 10.2: Specific Node Status
- **Command:** `aitbc blockchain status --node 2`
- **Description:** Check the status of node #2 in the local cluster.
- **Expected Output:** Status metrics specifically for the second node.

## 11. `blockchain supply`

**Command Description:** Get token supply information.

### Scenario 11.1: Total Supply
- **Command:** `aitbc blockchain supply`
- **Description:** View current token economics.
- **Expected Output:** Total minted supply, circulating supply, and burned tokens.

## 12. `blockchain sync-status`

**Command Description:** Get blockchain synchronization status.

### Scenario 12.1: Check Sync Progress
- **Command:** `aitbc blockchain sync-status`
- **Description:** Verify if the local node is fully synced with the network.
- **Expected Output:** Current block height vs highest known network block height, and a percentage progress indicator.

## 13. `blockchain transaction`

**Command Description:** Get transaction details.

### Scenario 13.1: Valid Transaction Lookup
- **Command:** `aitbc blockchain transaction <valid_tx_hash>`
- **Description:** Look up details for a known transaction.
- **Expected Output:** Detailed view of the transaction including sender, receiver, amount/data, gas used, and block inclusion.

## 14. `blockchain transactions`

**Command Description:** Get latest transactions on a chain.

### Scenario 14.1: Recent Chain Transactions
- **Command:** `aitbc blockchain transactions --chain-id ait-devnet`
- **Description:** View the mempool or recently confirmed transactions for a specific chain.
- **Expected Output:** A table listing recent transaction hashes, types, and status.

## 15. `blockchain validators`

**Command Description:** List blockchain validators.

### Scenario 15.1: Active Validators
- **Command:** `aitbc blockchain validators`
- **Description:** View the list of current active validators securing the network.
- **Expected Output:** A table of validator addresses, their total stake, uptime percentage, and voting power.
