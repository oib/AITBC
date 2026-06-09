"""
Server setup and execution for exchange API.
"""

import argparse
from http.server import HTTPServer

from aitbc import get_logger
from .database import init_db
from .handlers import ExchangeAPIHandler

logger = get_logger(__name__)


def run_server(port=8106):
    """Run the server"""
    init_db()

    server = HTTPServer(('localhost', port), ExchangeAPIHandler)
    logger.info("AITBC Exchange API Server started", port=port, url=f"http://localhost:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='AITBC Exchange API Server')
    parser.add_argument('--port', type=int, default=8106, help='Port to run the server on')
    args = parser.parse_args()
    run_server(port=args.port)
