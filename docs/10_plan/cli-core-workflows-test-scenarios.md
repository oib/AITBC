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
