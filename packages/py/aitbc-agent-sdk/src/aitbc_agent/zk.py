"""ZK operations using CLI commands"""


from aitbc.aitbc_logging import get_logger

from .command_executor import CommandExecutor

logger = get_logger(__name__)


class ZKOperations:
    """Zero-knowledge operations via CLI"""

    def __init__(self, cli_path: str = "/opt/aitbc/aitbc-click"):
        self.executor = CommandExecutor(cli_path)

    def generate_proof(self, input_data: str, circuit_id: str) -> str:
        """Generate ZK proof"""
        try:
            args = ["generate-proof", "--input", input_data, "--circuit", circuit_id]
            result = self.executor.execute_command("agent zk", args)
            if result["success"]:
                return result["data"].get("proof", "")
            else:
                logger.error("ZK generate_proof failed: %s", result.get('error'))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("generate_proof failed: %s", e)
            raise

    def verify_proof(self, proof: str, public_inputs: str) -> bool:
        """Verify ZK proof"""
        try:
            args = ["verify-proof", "--proof", proof, "--public-inputs", public_inputs]
            result = self.executor.execute_command("agent zk", args)
            if result["success"]:
                return result["data"].get("valid", False)
            else:
                logger.error("ZK verify_proof failed: %s", result.get('error'))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("verify_proof failed: %s", e)
            raise

    def create_receipt(self, proof: str, metadata: dict = None) -> str:
        """Create receipt from proof"""
        try:
            import json
            args = ["create-receipt", "--proof", proof]
            if metadata:
                args.extend(["--metadata", json.dumps(metadata)])
            result = self.executor.execute_command("agent zk", args)
            if result["success"]:
                return result["data"].get("receipt_id", "")
            else:
                logger.error("ZK create_receipt failed: %s", result.get('error'))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("create_receipt failed: %s", e)
            raise

    def submit_performance_proof(self, receipt: str, metrics: dict = None) -> str:
        """Submit performance proof"""
        try:
            import json
            args = ["submit-performance-proof", "--receipt", receipt]
            if metrics:
                args.extend(["--metrics", json.dumps(metrics)])
            result = self.executor.execute_command("agent zk", args)
            if result["success"]:
                return result["data"].get("submission_id", "")
            else:
                logger.error("ZK submit_performance_proof failed: %s", result.get('error'))
                raise Exception(result.get("error"))
        except Exception as e:
            logger.error("submit_performance_proof failed: %s", e)
            raise
