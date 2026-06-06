"""Messaging contract handlers."""

import json
import logging
import sys

import requests

logger = logging.getLogger(__name__)



def handle_messaging_deploy(args, default_rpc_url, render_mapping):
    """Handle messaging contract deployment."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    logger.info(f"Deploying messaging contract to {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        response = requests.post(f"{rpc_url}/rpc/contracts/deploy/messaging", json={}, params=params, timeout=30)
        if response.status_code == 200:
            result = response.json()
            logger.info("Messaging contract deployed successfully")
            render_mapping("Deployment result:", result)
        else:
            logger.error(f"Deployment failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error deploying messaging contract: {e}")
        sys.exit(1)


def handle_messaging_state(args, default_rpc_url, output_format, render_mapping):
    """Handle messaging contract state query."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    logger.info(f"Getting messaging contract state from {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        response = requests.get(f"{rpc_url}/rpc/contracts/messaging/state", params=params, timeout=10)
        if response.status_code == 200:
            state = response.json()
            if output_format(args) == "json":
                logger.info(json.dumps(state, indent=2))
            else:
                render_mapping("Messaging contract state:", state)
        else:
            logger.error(f"Query failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error getting contract state: {e}")
        sys.exit(1)


def handle_messaging_topics(args, default_rpc_url, output_format, render_mapping):
    """Handle forum topics query."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    logger.info(f"Getting forum topics from {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        response = requests.get(f"{rpc_url}/rpc/messaging/topics", params=params, timeout=10)
        if response.status_code == 200:
            topics = response.json()
            if output_format(args) == "json":
                logger.info(json.dumps(topics, indent=2))
            else:
                logger.info("Forum topics:")
                if isinstance(topics, list):
                    for topic in topics:
                        logger.info(f"  ID: {topic.get('topic_id', 'N/A')}, Title: {topic.get('title', 'N/A')}")
                else:
                    render_mapping("Topics:", topics)
        else:
            logger.error(f"Query failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error getting topics: {e}")
        sys.exit(1)


def handle_messaging_create_topic(args, default_rpc_url, read_password, render_mapping):
    """Handle forum topic creation."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    if not args.title or not args.content:
        logger.error("Error: --title and --content are required")
        sys.exit(1)

    # Get auth headers if wallet provided
    headers = {}
    if args.wallet:
        password = read_password(args)
        from keystore_auth import get_auth_headers
        headers = get_auth_headers(args.wallet, password, args.password_file)

    topic_data = {
        "title": args.title,
        "content": args.content,
    }
    if chain_id:
        topic_data["chain_id"] = chain_id

    logger.info(f"Creating forum topic on {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/messaging/topics/create", json=topic_data, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            logger.info("Topic created successfully")
            render_mapping("Topic:", result)
        else:
            logger.error(f"Creation failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error creating topic: {e}")
        sys.exit(1)


def handle_messaging_messages(args, default_rpc_url, output_format, render_mapping):
    """Handle messages query for a topic."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    if not args.topic_id:
        logger.error("Error: --topic-id is required")
        sys.exit(1)

    logger.info(f"Getting messages for topic {args.topic_id} from {rpc_url}...")
    try:
        params = {"topic_id": args.topic_id}
        if chain_id:
            params["chain_id"] = chain_id

        response = requests.get(f"{rpc_url}/rpc/messaging/topics/{args.topic_id}/messages", params=params, timeout=10)
        if response.status_code == 200:
            messages = response.json()
            if output_format(args) == "json":
                logger.info(json.dumps(messages, indent=2))
            else:
                logger.info(f"Messages for topic {args.topic_id}:")
                if isinstance(messages, list):
                    for msg in messages:
                        logger.info(f"  Message ID: {msg.get('message_id', 'N/A')}, Author: {msg.get('author', 'N/A')}")
                else:
                    render_mapping("Messages:", messages)
        else:
            logger.error(f"Query failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        sys.exit(1)


def handle_messaging_post(args, default_rpc_url, read_password, render_mapping):
    """Handle message posting to a topic."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    if not args.topic_id or not args.content:
        logger.error("Error: --topic-id and --content are required")
        sys.exit(1)

    # Get auth headers if wallet provided
    headers = {}
    if args.wallet:
        password = read_password(args)
        from keystore_auth import get_auth_headers
        headers = get_auth_headers(args.wallet, password, args.password_file)

    message_data = {
        "topic_id": args.topic_id,
        "content": args.content,
    }
    if chain_id:
        message_data["chain_id"] = chain_id

    logger.info(f"Posting message to topic {args.topic_id} on {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/messaging/messages/post", json=message_data, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            logger.info("Message posted successfully")
            render_mapping("Message:", result)
        else:
            logger.error(f"Post failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error posting message: {e}")
        sys.exit(1)


def handle_messaging_vote(args, default_rpc_url, read_password, render_mapping):
    """Handle voting on a message."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    if not args.message_id or not args.vote:
        logger.error("Error: --message-id and --vote are required")
        sys.exit(1)

    # Get auth headers if wallet provided
    headers = {}
    if args.wallet:
        password = read_password(args)
        from keystore_auth import get_auth_headers
        headers = get_auth_headers(args.wallet, password, args.password_file)

    vote_data = {
        "message_id": args.message_id,
        "vote": args.vote,
    }
    if chain_id:
        vote_data["chain_id"] = chain_id

    logger.info(f"Voting on message {args.message_id} on {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/messaging/messages/{args.message_id}/vote", json=vote_data, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            logger.info("Vote recorded successfully")
            render_mapping("Vote result:", result)
        else:
            logger.error(f"Vote failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error voting on message: {e}")
        sys.exit(1)


def handle_messaging_search(args, default_rpc_url, output_format, render_mapping):
    """Handle message search."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    if not args.query:
        logger.error("Error: --query is required")
        sys.exit(1)

    logger.info(f"Searching messages for '{args.query}' on {rpc_url}...")
    try:
        params = {"query": args.query}
        if chain_id:
            params["chain_id"] = chain_id

        response = requests.get(f"{rpc_url}/rpc/messaging/messages/search", params=params, timeout=30)
        if response.status_code == 200:
            results = response.json()
            if output_format(args) == "json":
                logger.info(json.dumps(results, indent=2))
            else:
                logger.info(f"Search results for '{args.query}':")
                if isinstance(results, list):
                    for msg in results:
                        logger.info(f"  Message ID: {msg.get('message_id', 'N/A')}, Topic: {msg.get('topic_id', 'N/A')}")
                else:
                    render_mapping("Search results:", results)
        else:
            logger.error(f"Search failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error searching messages: {e}")
        sys.exit(1)


def handle_messaging_reputation(args, default_rpc_url, output_format, render_mapping):
    """Handle agent reputation query."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    if not args.agent_id:
        logger.error("Error: --agent-id is required")
        sys.exit(1)

    logger.info(f"Getting reputation for agent {args.agent_id} from {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        response = requests.get(f"{rpc_url}/rpc/messaging/agents/{args.agent_id}/reputation", params=params, timeout=10)
        if response.status_code == 200:
            reputation = response.json()
            if output_format(args) == "json":
                logger.info(json.dumps(reputation, indent=2))
            else:
                render_mapping(f"Agent {args.agent_id} reputation:", reputation)
        else:
            logger.error(f"Query failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error getting reputation: {e}")
        sys.exit(1)


def handle_messaging_moderate(args, default_rpc_url, read_password, render_mapping):
    """Handle message moderation."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    if not args.message_id or not args.action:
        logger.error("Error: --message-id and --action are required")
        sys.exit(1)

    # Get auth headers if wallet provided
    headers = {}
    if args.wallet:
        password = read_password(args)
        from keystore_auth import get_auth_headers
        headers = get_auth_headers(args.wallet, password, args.password_file)

    moderation_data = {
        "message_id": args.message_id,
        "action": args.action,
    }
    if chain_id:
        moderation_data["chain_id"] = chain_id

    logger.info(f"Moderating message {args.message_id} on {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/messaging/messages/{args.message_id}/moderate", json=moderation_data, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            logger.info("Moderation action completed successfully")
            render_mapping("Moderation result:", result)
        else:
            logger.error(f"Moderation failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error moderating message: {e}")
        sys.exit(1)
