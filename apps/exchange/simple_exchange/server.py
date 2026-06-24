#!/usr/bin/env python3
"""Simple HTTP server for the AITBC Trade Exchange (stdlib http.server backend)."""

import argparse
from http.server import HTTPServer

from aitbc.aitbc_logging import configure_logging, get_logger

from .db import init_db
from .handlers import ExchangeAPIHandler

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


def main():
    parser = argparse.ArgumentParser(description="AITBC Exchange API Server")
    parser.add_argument("--port", type=int, default=8106, help="Port to run the server on")
    args = parser.parse_args()
    run_server(port=args.port)


if __name__ == "__main__":
    main()
