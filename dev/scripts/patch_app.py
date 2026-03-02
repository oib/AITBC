with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/app.py", "r") as f:
    content = f.read()

content = content.replace(
    """    _app_logger.info("Blockchain node started", extra={"chain_id": settings.chain_id})""",
    """    _app_logger.info("Blockchain node started", extra={"supported_chains": settings.supported_chains})"""
)

content = content.replace(
    """    @metrics_router.get("/health", tags=["health"], summary="Health check")
    async def health() -> dict:
        return {
            "status": "ok",
            "chain_id": settings.chain_id,
            "proposer_id": settings.proposer_id,
        }""",
    """    @metrics_router.get("/health", tags=["health"], summary="Health check")
    async def health() -> dict:
        return {
            "status": "ok",
            "supported_chains": [c.strip() for c in settings.supported_chains.split(",") if c.strip()],
            "proposer_id": settings.proposer_id,
        }"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/app.py", "w") as f:
    f.write(content)
