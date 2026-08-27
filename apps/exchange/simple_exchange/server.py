#!/usr/bin/env python3
"""CLI entry point for the AITBC Trade Exchange FastAPI service."""

import argparse

import uvicorn

from aitbc.aitbc_logging import configure_logging, get_logger

configure_logging(level="INFO", service_name="exchange", to_file=True)
logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="AITBC Exchange API Server")
    parser.add_argument("--port", type=int, default=8106, help="Port to run the server on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind the server to")
    args = parser.parse_args()

    logger.info("Starting AITBC Exchange API Server on %s:%s", args.host, args.port)
    # ponytail: Imported here so --help is fast; app triggers DB init via lifespan.
    from .main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="critical", access_log=False)


if __name__ == "__main__":
    main()
