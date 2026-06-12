import logging
import sys


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()

        # Add any extra arguments passed to the logger
        extra_fields = []
        if hasattr(record, "chain_id"):
            extra_fields.append(f"chain_id={record.chain_id}")
        if hasattr(record, "supported_chains"):
            extra_fields.append(f"supported_chains={record.supported_chains}")
        if hasattr(record, "height"):
            extra_fields.append(f"height={record.height}")
        if hasattr(record, "hash"):
            extra_fields.append(f"hash={record.hash}")
        if hasattr(record, "proposer"):
            extra_fields.append(f"proposer={record.proposer}")
        if hasattr(record, "error"):
            extra_fields.append(f"error={record.error}")

        if extra_fields:
            message = f"{message} [{', '.join(extra_fields)}]"

        return f"{record.levelname} {record.name} {message}"

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(TextFormatter())
        logger.addHandler(console_handler)

    return logger
