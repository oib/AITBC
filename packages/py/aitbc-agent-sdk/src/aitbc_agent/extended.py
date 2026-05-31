"""Extended Agent SDK operations using CLI commands"""


from aitbc.aitbc_logging import get_logger

from .command_executor import CommandExecutor

logger = get_logger(__name__)


class ExtendedOperations:
    """Extended operations via CLI commands"""

    def __init__(self, cli_path: str = "/opt/aitbc/aitbc-click"):
        self.executor = CommandExecutor(cli_path)

    def submit_ai_test(self, model_id: str, test_data: str) -> str:
        """Submit AI test job"""
        try:
            args = ["submit", "--model", model_id, "--test-data", test_data]
            result = self.executor.execute_command("ai", args)
            if result["success"]:
                return result["data"].get("job_id", "")
            else:
                logger.error(f"AI submit failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"submit_ai_test failed: {e}")
            raise

    def list_gpu(self, filters: dict = None) -> list[dict]:
        """List available GPU resources"""
        try:
            args = ["list"]
            if filters:
                for key, value in filters.items():
                    args.extend([f"--{key}", str(value)])
            result = self.executor.execute_command("market gpu", args)
            if result["success"]:
                return result["data"].get("listings", [])
            else:
                logger.error(f"GPU list failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"list_gpu failed: {e}")
            raise

    def create_swarm(self, name: str, max_agents: int) -> str:
        """Create agent swarm"""
        try:
            args = ["create", "--name", name, "--max-agents", str(max_agents)]
            result = self.executor.execute_command("swarm", args)
            if result["success"]:
                return result["data"].get("swarm_id", "")
            else:
                logger.error(f"Swarm create failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"create_swarm failed: {e}")
            raise

    def add_stake(self, amount: float, validator_id: str | None = None) -> str:
        """Add stake to validator"""
        try:
            args = ["manage", "--action", "add-stake", "--amount", str(amount)]
            if validator_id:
                args.extend(["--validator-id", validator_id])
            result = self.executor.execute_command("staking", args)
            if result["success"]:
                return result["data"].get("stake_id", "")
            else:
                logger.error(f"Staking add failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"add_stake failed: {e}")
            raise

    def create_island_bridge(self, name: str, source_chain: str, target_chain: str) -> str:
        """Create island bridge"""
        try:
            args = ["create", "--name", name, "--source", source_chain, "--target", target_chain]
            result = self.executor.execute_command("island", ["bridge"] + args)
            if result["success"]:
                return result["data"].get("bridge_id", "")
            else:
                logger.error(f"Island bridge create failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"create_island_bridge failed: {e}")
            raise

    def execute_bridge_transfer(self, bridge_id: str, amount: float, token: str) -> str:
        """Execute bridge transfer"""
        try:
            args = ["transfer", "--bridge-id", bridge_id, "--amount", str(amount), "--token", token]
            result = self.executor.execute_command("island", ["bridge"] + args)
            if result["success"]:
                return result["data"].get("transfer_id", "")
            else:
                logger.error(f"Bridge transfer failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"execute_bridge_transfer failed: {e}")
            raise

    def create_database(self, name: str, schema: str = "") -> str:
        """Create database"""
        try:
            args = ["init", "--name", name]
            if schema:
                args.extend(["--schema", schema])
            result = self.executor.execute_command("database", args)
            if result["success"]:
                return result["data"].get("database_id", "")
            else:
                logger.error(f"Database create failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"create_database failed: {e}")
            raise

    def query_database(self, database_id: str, query: str) -> list[dict]:
        """Query database"""
        try:
            args = ["query", "--database-id", database_id, "--query", query]
            result = self.executor.execute_command("database", args)
            if result["success"]:
                return result["data"].get("results", [])
            else:
                logger.error(f"Database query failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"query_database failed: {e}")
            raise

    def submit_training_job(self, model_id: str, dataset: str) -> str:
        """Submit training job"""
        try:
            args = ["submit", "--model", model_id, "--dataset", dataset]
            result = self.executor.execute_command("ai", ["training"] + args)
            if result["success"]:
                return result["data"].get("job_id", "")
            else:
                logger.error(f"Training submit failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"submit_training_job failed: {e}")
            raise

    def query_analytics(self, metrics: list[str], time_range: str = "24h") -> dict:
        """Query analytics"""
        try:
            args = ["query", "--metrics", ",".join(metrics), "--time-range", time_range]
            result = self.executor.execute_command("analytics", args)
            if result["success"]:
                return result["data"]
            else:
                logger.error(f"Analytics query failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"query_analytics failed: {e}")
            raise
