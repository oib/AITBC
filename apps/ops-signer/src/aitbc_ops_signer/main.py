"""Entry point: flag-gated. With AITBC_OPS_SIGNER_ENABLED unset the
service does nothing and exits 0 -- the shipped default is inert.
"""

from __future__ import annotations

import logging

from .config import ENABLED_FLAG, Config, enabled
from .server import OpsSignerServer

logger = logging.getLogger("aitbc_ops_signer")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    config = Config.from_env()
    if not enabled():
        logger.info("%s not set -- ops signer is inert, exiting", ENABLED_FLAG)
        return 0
    logger.info(
        "ops signer starting: sock=%s group=%s caps=%d/%d allow_file=%s",
        config.socket_path,
        config.peer_group,
        config.max_per_tx,
        config.max_per_day,
        config.allow_file,
    )
    OpsSignerServer(config).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
