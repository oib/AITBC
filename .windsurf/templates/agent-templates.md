# OpenClaw AITBC Agent Templates

> **Canonical validation**: Use [`docs/scenarios/VALIDATION.md`](../../docs/scenarios/VALIDATION.md) with `scripts/workflow/44_comprehensive_multi_node_scenario.sh` when validating these templates.

## Blockchain Monitor Agent
```json
{
  "name": "blockchain-monitor",
  "type": "monitoring",
  "description": "Monitors AITBC blockchain across multiple nodes",
  "version": "1.0.0",
  "config": {
    "nodes": ["aitbc", "aitbc1"],
    "check_interval": 30,
    "metrics": ["height", "transactions", "balance", "sync_status"],
    "alerts": {
      "height_diff": 5,
      "tx_failures": 3,
      "sync_timeout": 60
    }
  },
  "blockchain_integration": {
    "rpc_endpoints": {
      "aitbc": "http://localhost:8006",
      "aitbc1": "http://aitbc1:8006"
    },
    "wallet": "aitbc-user",
    "auto_transaction": true
  },
  "openclaw_config": {
    "model": "ollama/nemotron-3-super:cloud",
    "workspace": "blockchain-monitor",
    "routing": {
      "channels": ["blockchain", "monitoring"],
      "auto_respond": true
    }
  }
}
```

## Marketplace Trader Agent
```json
{
  "name": "marketplace-trader",
  "type": "trading",
  "description": "Automated agent marketplace trading bot",
  "version": "1.0.0",
  "config": {
    "budget": 1000,
    "max_price": 500,
    "preferred_agents": ["blockchain-analyzer", "data-processor"],
    "trading_strategy": "value_based",
    "risk_tolerance": 0.15
  },
  "blockchain_integration": {
    "payment_wallet": "aitbc-user",
    "auto_purchase": true,
    "profit_margin": 0.15,
    "max_positions": 5
  },
  "openclaw_config": {
    "model": "ollama/nemotron-3-super:cloud",
    "workspace": "marketplace-trader",
    "routing": {
      "channels": ["marketplace", "trading"],
      "auto_execute": true
    }
  }
}
```

## Blockchain Analyzer Agent
```json
{
  "name": "blockchain-analyzer",
  "type": "analysis",
  "description": "Advanced blockchain data analysis and insights",
  "version": "1.0.0",
  "config": {
    "analysis_depth": "deep",
    "metrics": ["transaction_patterns", "network_health", "token_flows"],
    "reporting_interval": 3600,
    "alert_thresholds": {
      "anomaly_detection": 0.95,
      "performance_degradation": 0.8
    }
  },
  "blockchain_integration": {
    "rpc_endpoints": ["http://localhost:8006", "http://aitbc1:8006"],
    "data_retention": 86400,
    "batch_processing": true
  },
  "openclaw_config": {
    "model": "ollama/nemotron-3-super:cloud",
    "workspace": "blockchain-analyzer",
    "routing": {
      "channels": ["analysis", "reporting"],
      "auto_generate_reports": true
    }
  }
}
```

## Multi-Node Coordinator Agent
```json
{
  "name": "multi-node-coordinator",
  "type": "coordination",
  "description": "Coordinates operations across multiple AITBC nodes",
  "version": "1.0.0",
  "config": {
    "nodes": ["aitbc", "aitbc1"],
    "coordination_strategy": "leader_follower",
    "sync_interval": 10,
    "failover_enabled": true
  },
  "blockchain_integration": {
    "primary_node": "aitbc",
    "backup_nodes": ["aitbc1"],
    "auto_failover": true,
    "health_checks": ["rpc", "sync", "transactions"]
  },
  "openclaw_config": {
    "model": "ollama/nemotron-3-super:cloud",
    "workspace": "multi-node-coordinator",
    "routing": {
      "channels": ["coordination", "health"],
      "auto_coordination": true
    }
  }
}
```

## Blockchain Messaging Agent
```json
{
  "name": "blockchain-messaging-agent",
  "type": "communication",
  "description": "Uses AITBC AgentMessagingContract for cross-node forum-style communication",
  "version": "1.0.0",
  "config": {
    "smart_contract": "AgentMessagingContract",
    "message_types": ["post", "reply", "announcement", "question", "answer"],
    "topics": ["coordination", "status-updates", "collaboration"],
    "reputation_target": 5,
    "auto_heartbeat_interval": 30
  },
  "blockchain_integration": {
    "rpc_endpoints": {
      "aitbc": "http://localhost:8006",
      "aitbc1": "http://aitbc1:8006"
    },
    "chain_id": "ait-mainnet",
    "cross_node_routing": true
  },
  "openclaw_config": {
    "model": "ollama/nemotron-3-super:cloud",
    "workspace": "blockchain-messaging",
    "routing": {
      "channels": ["messaging", "forum", "coordination"],
      "auto_respond": true
    }
  }
}
```
