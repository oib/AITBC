"""Stub contracts module for when contract_service is not available."""
from typing import Any, Dict
from fastapi import Request


async def _stub(request: Request, *args, **kwargs) -> Dict[str, Any]:
    return {"error": "Contract service not available", "status": "unavailable"}


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
