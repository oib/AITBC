"""Knowledge graph operations using CLI commands"""

import json

from aitbc.aitbc_logging import get_logger

from .command_executor import CommandExecutor

logger = get_logger(__name__)


class KnowledgeOperations:
    """Knowledge graph operations via CLI"""

    def __init__(self, cli_path: str = "/opt/aitbc/aitbc-click"):
        self.executor = CommandExecutor(cli_path)

    def create_knowledge_graph(self, name: str, description: str = "") -> str:
        """Create knowledge graph"""
        try:
            args = ["create", "--name", name]
            if description:
                args.extend(["--description", description])
            result = self.executor.execute_command("agent knowledge", args)
            if result["success"]:
                return result["data"].get("graph_id", "")
            else:
                logger.error(f"Knowledge create failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"create_knowledge_graph failed: {e}")
            raise

    def join_knowledge_graph(self, graph_id: str) -> bool:
        """Join knowledge graph"""
        try:
            args = ["join", "--graph-id", graph_id]
            result = self.executor.execute_command("agent knowledge", args)
            if result["success"]:
                return result["data"].get("joined", False)
            else:
                logger.error(f"Knowledge join failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"join_knowledge_graph failed: {e}")
            raise

    def query_knowledge_graph(self, graph_id: str, query: str) -> list[dict]:
        """Query knowledge graph"""
        try:
            args = ["query", "--graph-id", graph_id, "--query", query]
            result = self.executor.execute_command("agent knowledge", args)
            if result["success"]:
                return result["data"].get("results", [])
            else:
                logger.error(f"Knowledge query failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"query_knowledge_graph failed: {e}")
            raise

    def add_knowledge_node(self, graph_id: str, node_data: dict) -> str:
        """Add node to knowledge graph"""
        try:
            args = ["add-node", "--graph-id", graph_id, "--data", json.dumps(node_data)]
            result = self.executor.execute_command("agent knowledge", args)
            if result["success"]:
                return result["data"].get("node_id", "")
            else:
                logger.error(f"Knowledge add-node failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"add_knowledge_node failed: {e}")
            raise

    def add_knowledge_edge(self, graph_id: str, from_node: str, to_node: str, edge_data: dict = None) -> str:
        """Add edge to knowledge graph"""
        try:
            args = ["add-edge", "--graph-id", graph_id, "--from", from_node, "--to", to_node]
            if edge_data:
                args.extend(["--data", json.dumps(edge_data)])
            result = self.executor.execute_command("agent knowledge", args)
            if result["success"]:
                return result["data"].get("edge_id", "")
            else:
                logger.error(f"Knowledge add-edge failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"add_knowledge_edge failed: {e}")
            raise
