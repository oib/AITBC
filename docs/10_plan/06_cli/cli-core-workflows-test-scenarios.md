# Core CLI Workflows Test Scenarios

This document outlines test scenarios for the most commonly used, business-critical CLI commands that represent the core user journeys in the AITBC ecosystem.

## 1. Core Workflow: Client Job Submission Journey

This scenario traces a client's path from generating a job to receiving the computed result.

### Scenario 1.1: Submit a Job
- **Command:** `aitbc client submit --type inference --model "llama3" --data '{"prompt":"Hello AITBC"}'`
- **Description:** Submit a new AI inference job to the network.
- **Expected Output:** Success message containing the `job_id` and initial status (e.g., "pending").

### Scenario 1.2: Check Job Status
- **Command:** `aitbc client status <job_id>`
- **Description:** Poll the coordinator for the current status of the previously submitted job.
- **Expected Output:** Status indicating the job is queued, processing, or completed, along with details like assigned miner and timing.

### Scenario 1.3: Retrieve Job Result
- **Command:** `aitbc client result <job_id>`
- **Description:** Fetch the final output of a completed job.
- **Expected Output:** The computed result payload (e.g., the generated text from the LLM) and proof of execution if applicable.

---

## 2. Core Workflow: Miner Operations Journey

This scenario traces a miner's path from registering hardware to processing jobs.

### Scenario 2.1: Register as a Miner
- **Command:** `aitbc miner register --gpus "1x RTX 4090" --price-per-hour 0.5`
- **Description:** Register local hardware with the coordinator to start receiving jobs.
- **Expected Output:** Success message containing the assigned `miner_id` and confirmation of registered capabilities.

### Scenario 2.2: Poll for a Job
- **Command:** `aitbc miner poll`
- **Description:** Manually check the coordinator for an available job matching the miner's capabilities.
- **Expected Output:** If a job is available, details of the job (Job ID, type, payload) are returned and the job is marked as "processing" by this miner. If no job is available, a "no jobs in queue" message.

### Scenario 2.3: Mine with Local Ollama (Automated)
- **Command:** `aitbc miner mine-ollama --model llama3 --continuous`
- **Description:** Start an automated daemon that polls for jobs, executes them locally using Ollama, submits results, and repeats.
- **Expected Output:** Continuous log stream showing: polling -> job received -> local inference execution -> result submitted -> waiting.

---

## 3. Core Workflow: Wallet & Financial Operations

This scenario covers basic token management required to participate in the network.

### Scenario 3.1: Create a New Wallet
- **Command:** `aitbc wallet create --name test_wallet`
- **Description:** Generate a new local keypair and wallet address.
- **Expected Output:** Success message displaying the new wallet address and instructions to securely backup the seed phrase (which may be displayed once).

### Scenario 3.2: Check Wallet Balance
- **Command:** `aitbc wallet balance`
- **Description:** Query the blockchain for the current token balance of the active wallet.
- **Expected Output:** Display of available balance, staked balance, and total balance.

### Scenario 3.3: Client Job Payment
- **Command:** `aitbc client pay <job_id> --amount 10`
- **Description:** Authorize payment from the active wallet to fund a submitted job.
- **Expected Output:** Transaction hash confirming the payment, and the job status updating to "funded".

---

## 4. Core Workflow: GPU Marketplace

This scenario covers interactions with the decentralized GPU marketplace.

### Scenario 4.1: Register GPU on Marketplace
- **Command:** `aitbc marketplace gpu register --model "RTX 4090" --vram 24 --hourly-rate 0.5`
- **Description:** List a GPU on the open marketplace for direct rental or specific task assignment.
- **Expected Output:** Success message with a `listing_id` and confirmation that the offering is live on the network.

### Scenario 4.2: List Available GPU Offers
- **Command:** `aitbc marketplace offers list --model "RTX 4090"`
- **Description:** Browse the marketplace for available GPUs matching specific criteria.
- **Expected Output:** A table showing available GPUs, their providers, reputation scores, and hourly pricing.

### Scenario 4.3: Check Pricing Oracle
- **Command:** `aitbc marketplace pricing --model "RTX 4090"`
- **Description:** Get the current average, median, and suggested market pricing for a specific hardware model.
- **Expected Output:** Statistical breakdown of current market rates to help providers price competitively and users estimate costs.

---

## 5. Advanced Workflow: AI Agent Execution

This scenario covers the deployment of autonomous AI agents.

### Scenario 5.1: Create Agent Workflow
- **Command:** `aitbc agent create --name "data_analyzer" --type "analysis" --config agent_config.json`
- **Description:** Define a new agent workflow based on a configuration file.
- **Expected Output:** Success message with `agent_id` indicating the agent is registered and ready.

### Scenario 5.2: Execute Agent
- **Command:** `aitbc agent execute <agent_id> --input "Analyze Q3 financial data"`
- **Description:** Trigger the execution of the configured agent with a specific prompt/input.
- **Expected Output:** Streamed or final output showing the agent's thought process, actions taken (tool use), and final result.

---

## 6. Core Workflow: Governance & DAO

This scenario outlines how community members propose and vote on protocol changes.

### Scenario 6.1: Create a Proposal
- **Command:** `aitbc governance propose --title "Increase Miner Rewards" --description "Proposal to increase base reward by 5%" --amount 1000`
- **Description:** Submit a new governance proposal requiring a stake of 1000 tokens.
- **Expected Output:** Proposal successfully created with a `proposal_id` and voting timeline.

### Scenario 6.2: Vote on a Proposal
- **Command:** `aitbc governance vote <proposal_id> --vote "yes" --amount 500`
- **Description:** Cast a vote on an active proposal using staked tokens as voting power.
- **Expected Output:** Transaction hash confirming the vote has been recorded on-chain.

### Scenario 6.3: View Proposal Results
- **Command:** `aitbc governance result <proposal_id>`
- **Description:** Check the current standing or final result of a governance proposal.
- **Expected Output:** Tally of "yes" vs "no" votes, quorum status, and final decision if the voting period has ended.

---

## 7. Advanced Workflow: Agent Swarms

This scenario outlines collective agent operations.

### Scenario 7.1: Join an Agent Swarm
- **Command:** `aitbc swarm join --agent-id <agent_id> --task-type "distributed-training"`
- **Description:** Register an individual agent to participate in a collective swarm task.
- **Expected Output:** Confirmation that the agent has joined the swarm queue and is awaiting coordination.

### Scenario 7.2: Coordinate Swarm Execution
- **Command:** `aitbc swarm coordinate --task-id <task_id> --strategy "map-reduce"`
- **Description:** Dispatch a complex task to the assembled swarm using a specific processing strategy.
- **Expected Output:** Task successfully dispatched with tracking ID for swarm progress.

### Scenario 7.3: Achieve Swarm Consensus
- **Command:** `aitbc swarm consensus --task-id <task_id>`
- **Description:** Force or check the consensus mechanism for a completed swarm task to determine the final accepted output.
- **Expected Output:** The agreed-upon result reached by the majority of the swarm agents, with confidence metrics.

---

## 8. Deployment Operations

This scenario outlines managing the lifecycle of production deployments.

### Scenario 8.1: Create Deployment Configuration
- **Command:** `aitbc deploy create --name "prod-api" --image "aitbc-api:latest" --instances 3`
- **Description:** Define a new deployment target with 3 baseline instances.
- **Expected Output:** Deployment configuration successfully saved and validated.

### Scenario 8.2: Start Deployment
- **Command:** `aitbc deploy start "prod-api"`
- **Description:** Launch the configured deployment to the production cluster.
- **Expected Output:** Live status updates showing containers spinning up, health checks passing, and final "running" state.

### Scenario 8.3: Monitor Deployment
- **Command:** `aitbc deploy monitor "prod-api"`
- **Description:** View real-time resource usage and health of the active deployment.
- **Expected Output:** Interactive display of CPU, memory, and network I/O for the specified deployment.

---

## 9. Multi-Chain Node Management

This scenario outlines managing physical nodes across multiple chains.

### Scenario 9.1: Add Node Configuration
- **Command:** `aitbc node add --name "us-east-1" --host "10.0.0.5" --port 8080 --type "validator"`
- **Description:** Register a new infrastructure node into the local CLI context.
- **Expected Output:** Node successfully added to local configuration store.

### Scenario 9.2: Test Node Connectivity
- **Command:** `aitbc node test --node "us-east-1"`
- **Description:** Perform an active ping/health check against the specified node.
- **Expected Output:** Latency metrics, software version, and synced block height confirming the node is reachable and healthy.

### Scenario 9.3: List Hosted Chains
- **Command:** `aitbc node chains`
- **Description:** View a mapping of which configured nodes are currently hosting/syncing which network chains.
- **Expected Output:** A cross-referenced table showing nodes as rows, chains as columns, and sync status in the cells.

---

## 10. Cross-Chain Agent Communication

This scenario outlines how agents communicate and collaborate across different chains.

### Scenario 10.1: Register Agent in Network
- **Command:** `aitbc agent-comm register --agent-id <agent_id> --chain-id ait-devnet --capabilities "data-analysis"`
- **Description:** Register a local agent to the cross-chain communication network.
- **Expected Output:** Success message confirming agent is registered and discoverable on the network.

### Scenario 10.2: Discover Agents
- **Command:** `aitbc agent-comm discover --chain-id ait-healthchain --capability "medical-analysis"`
- **Description:** Search for available agents on another chain matching specific capabilities.
- **Expected Output:** List of matching agents, their network addresses, and current reputation scores.

### Scenario 10.3: Send Cross-Chain Message
- **Command:** `aitbc agent-comm send --target-agent <target_agent_id> --target-chain ait-healthchain --message "request_analysis"`
- **Description:** Send a direct message or task request to an agent on a different chain.
- **Expected Output:** Message transmission confirmation and delivery receipt.

---

## 11. Multi-Modal Agent Operations

This scenario outlines processing complex inputs beyond simple text.

### Scenario 11.1: Process Multi-Modal Input
- **Command:** `aitbc multimodal process --agent-id <agent_id> --image image.jpg --text "Analyze this chart"`
- **Description:** Submit a job to an agent containing both visual and text data.
- **Expected Output:** Job submission confirmation, followed by the agent's analysis integrating both data modalities.

### Scenario 11.2: Benchmark Capabilities
- **Command:** `aitbc multimodal benchmark --agent-id <agent_id>`
- **Description:** Run a standard benchmark suite to evaluate an agent's multi-modal processing speed and accuracy.
- **Expected Output:** Detailed performance report across different input types (vision, audio, text).

---

## 12. Autonomous Optimization

This scenario covers self-improving agent operations.

### Scenario 12.1: Enable Self-Optimization
- **Command:** `aitbc optimize self-opt --agent-id <agent_id> --target "inference-speed"`
- **Description:** Trigger an agent to analyze its own performance and adjust parameters to improve inference speed.
- **Expected Output:** Optimization started, followed by a report showing the parameter changes and measured performance improvement.

### Scenario 12.2: Predictive Scaling
- **Command:** `aitbc optimize predict --target "network-load" --horizon "24h"`
- **Description:** Use predictive models to forecast network load and recommend scaling actions.
- **Expected Output:** Time-series prediction and actionable recommendations for node scaling.

---

## 13. System Administration Operations

This scenario covers system administration and maintenance tasks for the AITBC infrastructure.

### Scenario 13.1: System Backup Operations
- **Command:** `aitbc admin backup --type full --destination /backups/aitbc-$(date +%Y%m%d)`
- **Description:** Create a complete system backup including blockchain data, configurations, and user data.
- **Expected Output:** Success message with backup file path, checksum verification, and estimated backup size. Progress indicators during backup creation.

### Scenario 13.2: View System Logs
- **Command:** `aitbc admin logs --service coordinator --tail 100 --level error`
- **Description:** Retrieve and filter system logs for specific services with severity level filtering.
- **Expected Output:** Formatted log output with timestamps, service names, log levels, and error messages. Options to follow live logs (`--follow`) or export to file (`--export`).

### Scenario 13.3: System Monitoring Dashboard
- **Command:** `aitbc admin monitor --dashboard --refresh 30`
- **Description:** Launch real-time system monitoring with configurable refresh intervals.
- **Expected Output:** Interactive dashboard showing:
  - CPU, memory, and disk usage across all nodes
  - Network throughput and latency metrics
  - Blockchain sync status and block production rate
  - Active jobs and queue depth
  - GPU utilization and temperature
  - Service health checks (coordinator, blockchain, marketplace)

### Scenario 13.4: Service Restart Operations
- **Command:** `aitbc admin restart --service blockchain-node --graceful --timeout 300`
- **Description:** Safely restart system services with graceful shutdown and timeout controls.
- **Expected Output:** Confirmation of service shutdown, wait for in-flight operations to complete, service restart, and health verification. Rollback option if restart fails.

### Scenario 13.5: System Status Overview
- **Command:** `aitbc admin status --verbose --format json`
- **Description:** Get comprehensive system status across all components and services.
- **Expected Output:** Detailed status report including:
  - Service availability (coordinator, blockchain, marketplace, monitoring)
  - Node health and connectivity status
  - Blockchain synchronization state
  - Database connection and replication status
  - Network connectivity and peer information
  - Resource utilization thresholds and alerts
  - Recent system events and warnings

### Scenario 13.6: System Update Operations
- **Command:** `aitbc admin update --component coordinator --version latest --dry-run`
- **Description:** Perform system updates with pre-flight checks and rollback capabilities.
- **Expected Output:** Update simulation showing:
  - Current vs target version comparison
  - Dependency compatibility checks
  - Required downtime estimate
  - Backup creation confirmation
  - Rollback plan verification
  - Update progress and post-update health checks

### Scenario 13.7: User Management Operations
- **Command:** `aitbc admin users --action list --role miner --status active`
- **Description:** Manage user accounts, roles, and permissions across the AITBC ecosystem.
- **Expected Output:** User management interface supporting:
  - List users with filtering by role, status, and activity
  - Create new users with role assignment
  - Modify user permissions and access levels
  - Suspend/activate user accounts
  - View user activity logs and audit trails
  - Export user reports for compliance

---

## 14. Emergency Response Scenarios

This scenario covers critical incident response and disaster recovery procedures.

### Scenario 14.1: Emergency Service Recovery
- **Command:** `aitbc admin restart --service all --emergency --force`
- **Description:** Emergency restart of all services during system outage or critical failure.
- **Expected Output:** Rapid service recovery with minimal downtime, error logging, and service dependency resolution.

### Scenario 14.2: Critical Log Analysis
- **Command:** `aitbc admin logs --level critical --since "1 hour ago" --alert`
- **Description:** Analyze critical system logs during emergency situations for root cause analysis.
- **Expected Output:** Prioritized critical errors, incident timeline, affected components, and recommended recovery actions.

### Scenario 14.3: System Health Check
- **Command:** `aitbc admin status --health-check --comprehensive --report`
- **Description:** Perform comprehensive system health assessment after incident recovery.
- **Expected Output:** Detailed health report with component status, performance metrics, security audit, and recovery recommendations.

---

## 15. Authentication & API Key Management

This scenario covers authentication workflows and API key management for secure access to AITBC services.

### Scenario 15.1: Import API Keys from Environment Variables
- **Command:** `aitbc auth import-env`
- **Description:** Import API keys from environment variables into the CLI configuration for seamless authentication.
- **Expected Output:** Success message confirming which API keys were imported and stored in the CLI configuration.
- **Prerequisites:** Environment variables `AITBC_API_KEY`, `AITBC_ADMIN_KEY`, or `AITBC_COORDINATOR_KEY` must be set.

### Scenario 15.2: Import Specific API Key Type
- **Command:** `aitbc auth import-env --key-type admin`
- **Description:** Import only admin-level API keys from environment variables.
- **Expected Output:** Confirmation that admin API key was imported and is available for privileged operations.
- **Prerequisites:** `AITBC_ADMIN_KEY` environment variable must be set with a valid admin API key (minimum 16 characters).

### Scenario 15.3: Import Client API Key
- **Command:** `aitbc auth import-env --key-type client`
- **Description:** Import client-level API keys for standard user operations.
- **Expected Output:** Confirmation that client API key was imported and is available for client operations.
- **Prerequisites:** `AITBC_API_KEY` or `AITBC_CLIENT_KEY` environment variable must be set.

### Scenario 15.4: Import with Custom Configuration Path
- **Command:** `aitbc auth import-env --config ~/.aitbc/custom_config.json`
- **Description:** Import API keys and store them in a custom configuration file location.
- **Expected Output:** Success message indicating the custom configuration path where keys were stored.
- **Prerequisites:** Custom directory path must exist and be writable.

### Scenario 15.5: Validate Imported API Keys
- **Command:** `aitbc auth validate`
- **Description:** Validate that imported API keys are properly formatted and can authenticate with the coordinator.
- **Expected Output:** Validation results showing:
  - Key format validation (length, character requirements)
  - Authentication test results against coordinator
  - Key type identification (admin vs client)
  - Expiration status if applicable

### Scenario 15.6: List Active API Keys
- **Command:** `aitbc auth list`
- **Description:** Display all currently configured API keys with their types and status.
- **Expected Output:** Table showing:
  - Key identifier (masked for security)
  - Key type (admin/client/coordinator)
  - Status (active/invalid/expired)
  - Last used timestamp
  - Associated permissions

### Scenario 15.7: Rotate API Keys
- **Command:** `aitbc auth rotate --key-type admin --generate-new`
- **Description:** Generate a new API key and replace the existing one with automatic cleanup.
- **Expected Output:** 
  - New API key generation confirmation
  - Old key deactivation notice
  - Update of local configuration
  - Instructions to update environment variables

### Scenario 15.8: Export API Keys (Secure)
- **Command:** `aitbc auth export --format env --output ~/aitbc_keys.env`
- **Description:** Export configured API keys to an environment file format for backup or migration.
- **Expected Output:** Secure export with:
  - Properly formatted environment variable assignments
  - File permissions set to 600 (read/write for owner only)
  - Warning about secure storage of exported keys
  - Checksum verification of exported file

### Scenario 15.9: Test API Key Permissions
- **Command:** `aitbc auth test --permissions`
- **Description:** Test the permissions associated with the current API key against various endpoints.
- **Expected Output:** Permission test results showing:
  - Client operations access (submit jobs, check status)
  - Admin operations access (user management, system config)
  - Read-only vs read-write permissions
  - Any restricted endpoints or rate limits

### Scenario 15.10: Handle Invalid API Keys
- **Command:** `aitbc auth import-env` (with invalid key in environment)
- **Description:** Test error handling when importing malformed or invalid API keys.
- **Expected Output:** Clear error message indicating:
  - Which key failed validation
  - Specific reason for failure (length, format, etc.)
  - Instructions for fixing the issue
  - Other keys that were successfully imported

### Scenario 15.11: Multi-Environment Key Management
- **Command:** `aitbc auth import-env --environment production`
- **Description:** Import API keys for a specific environment (development/staging/production).
- **Expected Output:** Environment-specific key storage with:
  - Keys tagged with environment identifier
  - Automatic context switching support
  - Validation against environment-specific endpoints
  - Clear indication of active environment

### Scenario 15.12: Revoke API Keys
- **Command:** `aitbc auth revoke --key-id <key_identifier> --confirm`
- **Description:** Securely revoke an API key both locally and from the coordinator service.
- **Expected Output:** Revocation confirmation with:
  - Immediate deactivation of the key
  - Removal from local configuration
  - Coordinator notification of revocation
  - Audit log entry for security compliance

### Scenario 15.13: Emergency Key Recovery
- **Command:** `aitbc auth recover --backup-file ~/aitbc_backup.enc`
- **Description:** Recover API keys from an encrypted backup file during emergency situations.
- **Expected Output:** Recovery process with:
  - Decryption of backup file (password protected)
  - Validation of recovered keys
  - Restoration of local configuration
  - Re-authentication test against coordinator

### Scenario 15.14: Audit API Key Usage
- **Command:** `aitbc auth audit --days 30 --detailed`
- **Description:** Generate a comprehensive audit report of API key usage over the specified period.
- **Expected Output:** Detailed audit report including:
  - Usage frequency and patterns
  - Accessed endpoints and operations
  - Geographic location of access (if available)
  - Any suspicious activity alerts
  - Recommendations for key rotation

---
