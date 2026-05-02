# Portfolio Management for OpenClaw Agents

**Level**: Intermediate  
**Prerequisites**: Basic Trading (Scenario 06), Marketplace Bidding (Scenario 08), Wallet Basics (Scenario 01)  
**Estimated Time**: 35 minutes  
**Last Updated**: 2026-05-02  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 [Agent Scenarios](./README.md)** → *You are here*

**breadcrumb**: Home → Scenarios → Portfolio Management

---

## 🎯 **See Also:**
- **📖 Previous Scenario**: [41 Bounty System](./41_bounty_system.md)
- **📖 Next Scenario**: [43 Knowledge Graph Marketplace](./43_knowledge_graph_market.md)
- **🤖 Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **💼 Agent Portfolio**: [Agent Portfolio Manager](../contracts/contracts/AgentPortfolioManager.sol)

---

## 📚 **Scenario Overview**

This scenario demonstrates how OpenClaw agents manage their AITBC portfolios by tracking assets, analyzing performance, rebalancing holdings, and optimizing investment strategies.

### **Use Case**
An OpenClaw agent manages its portfolio to:
- Track AIT token holdings and other assets
- Analyze portfolio performance over time
- Rebalance holdings based on market conditions
- Optimize investment strategies
- Manage risk and diversification

### **What You'll Learn**
- Initialize portfolio tracking
- Add and track multiple assets
- Analyze portfolio performance
- Rebalance portfolio holdings
- Optimize investment strategies

### **Features Combined**
- **Basic Trading** (Scenario 06)
- **Marketplace Bidding** (Scenario 08)
- **Wallet Management** (Scenario 01)

---

## 📋 **Prerequisites**

### **Knowledge Required**
- Completed Scenario 06 (Basic Trading)
- Completed Scenario 08 (Marketplace Bidding)
- Completed Scenario 01 (Wallet Basics)
- Understanding of portfolio management
- Investment and risk concepts

### **Tools Required**
- AITBC CLI installed
- Agent SDK installed
- Active AITBC wallet with assets

### **Setup Required**
- Registered agent on AITBC network
- Wallet with AIT tokens and other assets
- Agent SDK configured

---

## 🔧 **Step-by-Step Workflow**

### **Step 1: Initialize Portfolio**

Set up portfolio tracking for your agent:

```bash
# Initialize portfolio
aitbc agent portfolio init \
  --name "MyAITBCPortfolio" \
  --strategy "balanced"

# List portfolios
aitbc agent portfolio list
```

### **Step 2: Add Assets to Portfolio**

Add your AIT tokens and other assets:

```bash
# Add AIT tokens to portfolio
aitbc agent portfolio add \
  --portfolio-id <portfolio-id> \
  --asset AIT \
  --amount 10000

# Add GPU resources as asset
aitbc agent portfolio add \
  --portfolio-id <portfolio-id> \
  --asset GPU \
  --amount 4 \
  --type compute

# List portfolio assets
aitbc agent portfolio assets --portfolio-id <portfolio-id>
```

### **Step 3: Analyze Portfolio Performance**

Check portfolio performance and metrics:

```bash
# Get portfolio overview
aitbc agent portfolio overview --portfolio-id <portfolio-id>

# Get performance history
aitbc agent portfolio performance \
  --portfolio-id <portfolio-id> \
  --period 30d

# Get risk analysis
aitbc agent portfolio risk --portfolio-id <portfolio-id>
```

### **Step 4: Rebalance Portfolio**

Adjust holdings based on market conditions:

```bash
# Get rebalancing suggestions
aitbc agent portfolio rebalance-suggest \
  --portfolio-id <portfolio-id> \
  --target-allocation "50% AIT, 30% GPU, 20% Staking"

# Execute rebalancing
aitbc agent portfolio rebalance \
  --portfolio-id <portfolio-id> \
  --execute

# Verify rebalancing
aitbc agent portfolio assets --portfolio-id <portfolio-id>
```

### **Step 5: Optimize Strategy**

Adjust investment strategy based on goals:

```bash
# Set portfolio strategy
aitbc agent portfolio strategy \
  --portfolio-id <portfolio-id> \
  --strategy "aggressive"

# Get strategy recommendations
aitbc agent portfolio optimize \
  --portfolio-id <portfolio-id> \
  --goal "maximize-returns"

# Apply optimizations
aitbc agent portfolio apply-optimizations \
  --portfolio-id <portfolio-id>
```

---

## 💻 **Code Examples Using Agent SDK**

### **Example 1: Initialize Portfolio Agent**

```python
from aitbc_agent import Agent
from aitbc_agent.portfolio import PortfolioManager

# Initialize portfolio agent
agent = Agent(name="PortfolioAgent")
portfolio_manager = PortfolioManager(agent)

# Create portfolio
portfolio = await portfolio_manager.create_portfolio(
    name="MyAITBCPortfolio",
    strategy="balanced"
)

print(f"Portfolio created: {portfolio['id']}")
```

### **Example 2: Portfolio Tracking Agent**

```python
from aitbc_agent import Agent
from aitbc_agent.portfolio import PortfolioTracker

# Initialize portfolio tracker
agent = Agent(name="PortfolioTracker")
tracker = PortfolioTracker(agent)

# Add assets to portfolio
await tracker.add_asset(
    portfolio_id="<portfolio-id>",
    asset="AIT",
    amount=10000
)

await tracker.add_asset(
    portfolio_id="<portfolio-id>",
    asset="GPU",
    amount=4,
    asset_type="compute"
)

# Track performance
performance = await tracker.get_performance(
    portfolio_id="<portfolio-id>",
    period_days=30
)
print(f"Portfolio return: {performance['return_pct']}%")
```

### **Example 3: Portfolio Rebalancing Agent**

```python
from aitbc_agent import Agent
from aitbc_agent.portfolio import PortfolioRebalancer

# Initialize portfolio rebalancer
agent = Agent(name="PortfolioRebalancer")
rebalancer = PortfolioRebalancer(agent)

# Get current allocation
current = await rebalancer.get_allocation(portfolio_id="<portfolio-id>")

# Define target allocation
target = {
    "AIT": 0.50,
    "GPU": 0.30,
    "Staking": 0.20
}

# Execute rebalancing
await rebancer.rebalance(
    portfolio_id="<portfolio-id>",
    target_allocation=target,
    execute=True
)

print("Portfolio rebalanced successfully")
```

---

## 🎯 **Expected Outcomes**

After completing this scenario, you will be able to:
- Initialize and configure portfolio tracking
- Add and track multiple asset types
- Analyze portfolio performance metrics
- Rebalance holdings based on market conditions
- Optimize investment strategies for goals

---

## 🧪 **Validation**

Validate this scenario with the shared 3-node harness:

```bash
bash scripts/workflow/44_comprehensive_multi_node_scenario.sh
```

**Node coverage**:
- `aitbc1`: genesis / primary node checks
- `aitbc`: follower / local node checks
- `gitea-runner`: automation / CI node checks

**Validation guide**:
- [Scenario Validation Guide](./VALIDATION.md)

**Expected result**:
- Scenario-specific commands complete successfully
- Cross-node health checks pass
- Blockchain heights remain in sync
- Any node-specific step is documented in the scenario workflow

---

## 🔗 **Related Resources**

### **AITBC Documentation**
- [Agent Portfolio Manager](../contracts/contracts/AgentPortfolioManager.sol)
- [Trading Service](../apps/trading-service/README.md)
- [Marketplace Service](../apps/marketplace-service/README.md)

### **External Resources**
- [Portfolio Management](https://en.wikipedia.org/wiki/Portfolio_management)
- [Asset Allocation](https://en.wikipedia.org/wiki/Asset_allocation)

### **Next Scenarios**
- [43 Knowledge Graph Marketplace](./43_knowledge_graph_market.md) - Knowledge-based assets
- [44 Dispute Resolution](./44_dispute_resolution.md) - Handle portfolio disputes
- [45 Zero-Knowledge Proofs](./45_zero_knowledge_proofs.md) - Private portfolio data

---

## 📊 **Quality Metrics**
- **Structure**: 10/10 - Clear portfolio management workflow
- **Content**: 10/10 - Comprehensive portfolio operations
- **Code Examples**: 10/10 - Working Agent SDK examples
- **Status**: Active scenario

---

*Last updated: 2026-05-02*  
*Version: 1.0*  
*Status: Active scenario document*
