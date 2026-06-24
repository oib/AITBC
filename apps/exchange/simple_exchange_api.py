#!/usr/bin/env python3
"""
Simple FastAPI backend for the AITBC Trade Exchange (Python 3.13 compatible)
"""

import argparse
from http.server import HTTPServer

from aitbc.aitbc_logging import configure_logging, get_logger

from db import init_db  # noqa: E402
from handlers import ExchangeAPIHandler  # noqa: E402

configure_logging(level="INFO", service_name="exchange", to_file=True)
logger = get_logger(__name__)


def run_server(port=8106):
    """Run the server"""
    init_db()
    # Removed mock trades - now using only real blockchain data

    server = HTTPServer(("localhost", port), ExchangeAPIHandler)
    logger.info("AITBC Exchange API Server started on port %s (http://localhost:%s)", port, port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AITBC Exchange API Server")
    parser.add_argument("--port", type=int, default=8106, help="Port to run the server on")
    args = parser.parse_args()
    run_server(port=args.port)
