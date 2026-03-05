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
