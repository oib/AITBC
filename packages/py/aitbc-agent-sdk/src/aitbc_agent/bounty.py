"""Bounty operations using CLI commands"""


from aitbc.aitbc_logging import get_logger

from .command_executor import CommandExecutor

logger = get_logger(__name__)


class BountyOperations:
    """Bounty operations via CLI"""

    def __init__(self, cli_path: str = "/opt/aitbc/aitbc-click"):
        self.executor = CommandExecutor(cli_path)

    def create_bounty(self, title: str, description: str, reward: float) -> str:
        """Create bounty"""
        try:
            args = ["create", "--title", title, "--description", description, "--reward", str(reward)]
            result = self.executor.execute_command("agent bounty", args)
            if result["success"]:
                return result["data"].get("bounty_id", "")
            else:
                logger.error(f"Bounty create failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"create_bounty failed: {e}")
            raise

    def list_bounties(self, status: str = "open") -> list[dict]:
        """List bounties"""
        try:
            args = ["list", "--status", status]
            result = self.executor.execute_command("agent bounty", args)
            if result["success"]:
                return result["data"].get("bounties", [])
            else:
                logger.error(f"Bounty list failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"list_bounties failed: {e}")
            raise

    def submit_bounty_solution(self, bounty_id: str, solution: str) -> str:
        """Submit bounty solution"""
        try:
            args = ["submit", "--bounty-id", bounty_id, "--solution", solution]
            result = self.executor.execute_command("agent bounty", args)
            if result["success"]:
                return result["data"].get("submission_id", "")
            else:
                logger.error(f"Bounty submit failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"submit_bounty_solution failed: {e}")
            raise

    def claim_bounty(self, bounty_id: str) -> bool:
        """Claim bounty reward"""
        try:
            args = ["claim", "--bounty-id", bounty_id]
            result = self.executor.execute_command("agent bounty", args)
            if result["success"]:
                return result["data"].get("claimed", False)
            else:
                logger.error(f"Bounty claim failed: {result.get('error')}")
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error(f"claim_bounty failed: {e}")
            raise
