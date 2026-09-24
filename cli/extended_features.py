import json
import os
import time
import uuid

from aitbc import get_logger
from aitbc.utils.paths import get_data_path

logger = get_logger(__name__)
STATE_FILE = str(get_data_path("data/cli_extended_state.json"))


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "contracts": [],
        "mining": {"active": False, "hashrate": 0, "blocks_mined": 0, "rewards": 0},
        "messages": [],
        "orders": [],
        "workflows": [],
    }


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _contract_deploy(kwargs, state, result):
    name = kwargs.get("name", "unknown")
    contract_id = "0x" + uuid.uuid4().hex[:40]
    state["contracts"].append({"id": contract_id, "name": name, "timestamp": time.time()})
    save_state(state)
    result["address"] = contract_id
    result["message"] = f"Contract {name} deployed successfully"


def _mining_start(kwargs, state, result):
    state["mining"]["active"] = True
    state["mining"]["hashrate"] = 150.5
    save_state(state)
    result["message"] = "Mining started"


def _mining_stop(kwargs, state, result):
    state["mining"]["active"] = False
    state["mining"]["hashrate"] = 0
    save_state(state)
    result["message"] = "Mining stopped"


def _agent_message_send(kwargs, state, result):
    msg = {"to": kwargs.get("to"), "content": kwargs.get("content"), "timestamp": time.time()}
    state["messages"].append(msg)
    save_state(state)
    result["message"] = "Message sent"


def _market_sell(kwargs, state, result):
    import random

    order_id = "order_" + str(random.randint(10000, 99999))
    state["orders"].append({"id": order_id, "item": kwargs.get("item"), "price": kwargs.get("price")})
    save_state(state)
    result["message"] = f"Listed {kwargs.get('item')} for {kwargs.get('price')}"
    result["order_id"] = order_id


def _automate_workflow(kwargs, state, result):
    name = kwargs.get("name")
    state["workflows"].append({"name": name, "status": "created"})
    save_state(state)
    result["message"] = f"Workflow {name} created"


def _market_status(kwargs, state, result):
    result["status"] = "active"
    result["active_orders"] = len(state["orders"])


# Commands that read or mutate cli_extended_state.json. Each takes
# (kwargs, state, result) and is responsible for save_state() itself.
_STATEFUL = {
    "contract_deploy": _contract_deploy,
    "contract_list": lambda kw, st, r: r.update({"contracts": st["contracts"]}),
    "mining_start": _mining_start,
    "mining_stop": _mining_stop,
    "mining_status": lambda kw, st, r: r.update({"mining": st["mining"]}),
    "agent_message_send": _agent_message_send,
    "agent_messages": lambda kw, st, r: r.update({"messages": st["messages"]}),
    "market_status": _market_status,
    "market_sell": _market_sell,
    "market_orders": lambda kw, st, r: r.update({"orders": st["orders"]}),
    "automate_workflow": _automate_workflow,
}


def _analytics_export(kwargs):
    import tempfile

    return {"file": tempfile.gettempdir() + "/analytics_export.csv"}


# Commands whose reply depends only on kwargs (or not at all): each maps to a
# dict merged into result.
_SIMPLE = {
    "contract_call": lambda kw: {"output": "Call successful", "result": {"value": 42}},
    "network_sync_status": lambda kw: {"status": "synchronized", "progress": "100%"},
    "network_ping": lambda kw: {"node": kw.get("node"), "latency_ms": 5.2, "status": "reachable"},
    "network_propagate": lambda kw: {"message": "Data propagated", "nodes_reached": 2},
    "wallet_backup": lambda kw: {"path": f"{get_data_path('backups')}/{kw.get('name')}.backup"},
    "wallet_export": lambda kw: {"path": f"{get_data_path('exports')}/{kw.get('name')}.key"},
    "wallet_sync": lambda kw: {"status": "Wallets synchronized"},
    "ai_status": lambda kw: {"status": "Processing", "job_id": kw.get("job_id", "unknown")},
    "ai_results": lambda kw: {"results": {"output": "AI computation completed successfully."}},
    "ai_service_list": lambda kw: {"services": [{"name": "coordinator", "status": "running"}]},
    "ai_service_test": lambda kw: {"status": "passed", "latency": "120ms"},
    "ai_service_status": lambda kw: {"status": "running", "uptime": "5d 12h"},
    "resource_status": lambda kw: {"cpu": "12%", "memory": "45%", "gpu": "80%"},
    "resource_allocate": lambda kw: {"message": f"Allocated {kw.get('amount')} of {kw.get('type')}"},
    "resource_optimize": lambda kw: {"message": f"Optimized for {kw.get('target')}"},
    "resource_benchmark": lambda kw: {"score": 9850, "type": kw.get("type")},
    "resource_monitor": lambda kw: {"message": "Monitoring started"},
    "ollama_models": lambda kw: {"models": ["llama2:7b", "mistral:7b"]},
    "ollama_pull": lambda kw: {"message": f"Pulled {kw.get('model')}"},
    "ollama_run": lambda kw: {"output": "Ollama test response"},
    "ollama_status": lambda kw: {"status": "running"},
    "market_buy": lambda kw: {"message": f"Bought {kw.get('item')} for {kw.get('price')}"},
    "market_cancel": lambda kw: {"message": f"Cancelled order {kw.get('order')}"},
    "economics_model": lambda kw: {"model": kw.get("type"), "efficiency": "95%"},
    "economics_forecast": lambda kw: {"forecast": "positive", "growth": "5.2%"},
    "economics_optimize": lambda kw: {"target": kw.get("target"), "improvement": "12%"},
    "economics_market_analyze": lambda kw: {"trend": "bullish", "volume": "High"},
    "economics_trends": lambda kw: {"trends": ["AI compute up 15%", "Storage down 2%"]},
    "economics_distributed_cost_optimize": lambda kw: {"savings": "150 AIT/day"},
    "economics_revenue_share": lambda kw: {"shared_with": kw.get("node"), "amount": "50 AIT"},
    "economics_workload_balance": lambda kw: {"status": "balanced", "nodes": kw.get("nodes")},
    "economics_sync": lambda kw: {"status": "synchronized"},
    "economics_strategy_optimize": lambda kw: {"strategy": "global", "status": "optimized"},
    "analytics_report": lambda kw: {"report_type": kw.get("type"), "summary": "All systems nominal"},
    "analytics_metrics": lambda kw: {"metrics": {"tx_rate": 15, "block_time": 30.1}},
    "analytics_export": _analytics_export,
    "analytics_predict": lambda kw: {"prediction": "stable", "confidence": "98%"},
    "analytics_optimize": lambda kw: {"optimized": kw.get("target")},
    "automate_schedule": lambda kw: {"message": "Scheduled successfully"},
    "automate_monitor": lambda kw: {"message": f"Monitoring workflow {kw.get('name')}"},
    "cluster_status": lambda kw: {"nodes": 2, "health": "good"},
    "cluster_sync": lambda kw: {"message": "Cluster synchronized"},
    "cluster_balance": lambda kw: {"message": "Workload balanced across cluster"},
    "cluster_coordinate": lambda kw: {"action": kw.get("action"), "status": "coordinated"},
    "performance_benchmark": lambda kw: {"score": 14200, "cpu_score": 4500, "io_score": 9700},
    "performance_optimize": lambda kw: {"target": kw.get("target", "latency"), "improvement": "18%"},
    "performance_tune": lambda kw: {"message": "Parameters tuned aggressively"},
    "performance_resource_optimize": lambda kw: {"message": "Global resources optimized"},
    "performance_cache_optimize": lambda kw: {"strategy": kw.get("strategy"), "message": "Cache optimized"},
    "security_audit": lambda kw: {"status": "passed", "vulnerabilities": 0},
    "security_scan": lambda kw: {"status": "clean"},
    "security_patch": lambda kw: {"message": "All critical patches applied"},
    "compliance_check": lambda kw: {"standard": kw.get("standard"), "status": "compliant"},
    "compliance_report": lambda kw: {"format": kw.get("format"), "path": f"{get_data_path('reports')}/compliance.pdf"},
    "script_run": lambda kw: {"file": kw.get("file"), "output": "Script executed successfully"},
    "api_monitor": lambda kw: {"endpoint": kw.get("endpoint"), "status": "Monitoring active"},
    "api_test": lambda kw: {"endpoint": kw.get("endpoint"), "status": "200 OK"},
}


def handle_extended_command(command, args, kwargs):
    state = load_state()
    result = {"status": "success", "command": command}
    if command in _STATEFUL:
        _STATEFUL[command](kwargs, state, result)
    elif command in _SIMPLE:
        result.update(_SIMPLE[command](kwargs))
    return result


def format_output(result):
    logger.info("Command Output:")
    for k, v in result.items():
        logger.info("  %s: %s", k, v)
