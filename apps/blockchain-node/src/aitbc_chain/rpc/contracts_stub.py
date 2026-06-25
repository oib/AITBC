"""Stub contracts module for when contract_service is not available.

This stub never returns fake data.  Every function raises an explicit
``HTTPException`` with status 503 so that callers receive a clear error
instead of a misleading success response.  In normal operation the real
``contracts`` module is imported by ``router.py``; this module only exists
as a safety net for direct imports and always fails loudly.
"""

from typing import Any

from fastapi import HTTPException, Request


async def _stub(request: Request, *args: Any, **kwargs: Any) -> dict[str, Any]:
    raise HTTPException(status_code=503, detail="Contract service not available")


deploy_messaging_contract = _stub
list_contracts = _stub
deploy_contract = _stub
call_contract = _stub
verify_contract = _stub
get_messaging_contract_state = _stub
get_forum_topics = _stub
create_forum_topic = _stub
get_topic_messages = _stub
post_message = _stub
vote_message = _stub
search_messages = _stub
get_agent_reputation = _stub
moderate_message = _stub
