"""Dispute operations using CLI commands"""

from aitbc.aitbc_logging import get_logger

from .command_executor import CommandExecutor

logger = get_logger(__name__)


class DisputeOperations:
    """Dispute operations via CLI"""

    def __init__(self, cli_path: str = "/opt/aitbc/aitbc-click"):
        self.executor = CommandExecutor(cli_path)

    def file_dispute(self, title: str, description: str, evidence: str) -> str:
        """File dispute"""
        try:
            args = ["file", "--title", title, "--description", description, "--evidence", evidence]
            result = self.executor.execute_command("agent dispute", args)
            if result["success"]:
                return result["data"].get("dispute_id", "")
            else:
                logger.error("Dispute file failed: %s", result.get("error"))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("file_dispute failed: %s", e)
            raise

    def register_arbitrator(self, arbitrator_id: str) -> bool:
        """Register as arbitrator"""
        try:
            args = ["register-arbitrator", "--arbitrator-id", arbitrator_id]
            result = self.executor.execute_command("agent dispute", args)
            if result["success"]:
                return result["data"].get("registered", False)
            else:
                logger.error("Dispute register-arbitrator failed: %s", result.get("error"))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("register_arbitrator failed: %s", e)
            raise

    def submit_dispute_evidence(self, dispute_id: str, evidence: str) -> bool:
        """Submit dispute evidence"""
        try:
            args = ["evidence", "--dispute-id", dispute_id, "--evidence", evidence]
            result = self.executor.execute_command("agent dispute", args)
            if result["success"]:
                return result["data"].get("submitted", False)
            else:
                logger.error("Dispute evidence failed: %s", result.get("error"))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("submit_dispute_evidence failed: %s", e)
            raise

    def vote_dispute(self, dispute_id: str, vote: bool, reason: str = "") -> bool:
        """Vote on dispute"""
        try:
            args = ["vote", "--dispute-id", dispute_id, "--vote", "true" if vote else "false"]
            if reason:
                args.extend(["--reason", reason])
            result = self.executor.execute_command("agent dispute", args)
            if result["success"]:
                return result["data"].get("accepted", False)
            else:
                logger.error("Dispute vote failed: %s", result.get("error"))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("vote_dispute failed: %s", e)
            raise
