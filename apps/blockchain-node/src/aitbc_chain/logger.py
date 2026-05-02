import logging
import sys
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime, timezone

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        
        # Add any extra arguments passed to the logger
        if hasattr(record, "chain_id"):
            log_record["chain_id"] = record.chain_id
        if hasattr(record, "supported_chains"):
            log_record["supported_chains"] = record.supported_chains
        if hasattr(record, "height"):
            log_record["height"] = record.height
        if hasattr(record, "hash"):
            log_record["hash"] = record.hash
        if hasattr(record, "proposer"):
            log_record["proposer"] = record.proposer
        if hasattr(record, "error"):
            log_record["error"] = record.error
            
        return json.dumps(log_record)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(JsonFormatter())
        logger.addHandler(console_handler)
        
    return logger
