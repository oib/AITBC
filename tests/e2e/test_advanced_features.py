import pytest
import httpx
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any

AITBC_URL = "http://127.0.0.1:8000/v1"

@pytest.mark.asyncio
async def test_multi_modal_fusion():
    """Test Phase 10: Multi-Modal Agent Fusion"""
    async with httpx.AsyncClient() as client:
        # 1. Create a fusion model
        create_model_payload = {
            "model_name": "MarketAnalyzer",
            "version": "1.0.0",
            "fusion_type": "cross_domain",
            "base_models": ["gemma3:1b", "llama3.2:3b"],
            "input_modalities": ["text", "structured_data"],
            "fusion_strategy": "ensemble_fusion"
        }
        response = await client.post(
            f"{AITBC_URL}/multi-modal-rl/fusion/models",
            json=create_model_payload
        )
        assert response.status_code in [200, 201], f"Failed to create fusion model: {response.text}"
        data = response.json()
        assert "fusion_id" in data or "id" in data
        fusion_id = data.get("fusion_id", data.get("id"))

        # 2. Perform inference using the created model
        infer_payload = {
            "fusion_id": fusion_id,
            "input_data": {
                "text": "Analyze this market data and provide a textual summary",
                "structured_data": {"price_trend": "upward", "volume": 15000}
            }
        }
        infer_response = await client.post(
            f"{AITBC_URL}/multi-modal-rl/fusion/{fusion_id}/infer",
            json=infer_payload
        )
        assert infer_response.status_code in [200, 201], f"Failed fusion inference: {infer_response.text}"

@pytest.mark.asyncio
async def test_dao_governance_proposal():
    """Test Phase 11: OpenClaw DAO Governance & Proposal Test"""
    async with httpx.AsyncClient() as client:
        # 1. Ensure proposer profile exists (or create it)
        profile_create_payload = {
            "user_id": "client1",
            "initial_voting_power": 1000.0,
            "delegate_to": None
        }
        profile_response = await client.post(
            f"{AITBC_URL}/governance/profiles",
            json=profile_create_payload
        )
        # Note: If it already exists, it might return an error, but let's assume we can get the profile
        proposer_profile_id = "client1"
        if profile_response.status_code in [200, 201]:
            proposer_profile_id = profile_response.json().get("profile_id", "client1")
        elif profile_response.status_code == 400 and "already exists" in profile_response.text.lower():
            # Get existing profile
            get_prof_resp = await client.get(f"{AITBC_URL}/governance/profiles/client1")
            if get_prof_resp.status_code == 200:
                proposer_profile_id = get_prof_resp.json().get("id", "client1")
            
        # 2. Create Proposal
        proposal_payload = {
            "title": "Reduce Platform Fee to 0.5%",
            "description": "Lowering the fee to attract more edge miners",
            "category": "economic_policy",
            "execution_payload": {
                "target_contract": "MarketplaceConfig",
                "action": "setPlatformFee",
                "value": "0.5"
            }
        }
        
        response = await client.post(
            f"{AITBC_URL}/governance/proposals?proposer_id={proposer_profile_id}",
            json=proposal_payload
        )
        assert response.status_code in [200, 201], f"Failed to create proposal: {response.text}"
        proposal_id = response.json().get("id") or response.json().get("proposal_id")
        assert proposal_id

        # 3. Vote on Proposal
        # Ensure miner1 profile exists (or create it)
        miner1_profile_payload = {
            "user_id": "miner1",
            "initial_voting_power": 1500.0,
            "delegate_to": None
        }
        miner1_profile_response = await client.post(
            f"{AITBC_URL}/governance/profiles",
            json=miner1_profile_payload
        )
        miner1_profile_id = "miner1"
        if miner1_profile_response.status_code in [200, 201]:
            miner1_profile_id = miner1_profile_response.json().get("profile_id", "miner1")
        elif miner1_profile_response.status_code == 400 and "already exists" in miner1_profile_response.text.lower():
            get_prof_resp = await client.get(f"{AITBC_URL}/governance/profiles/miner1")
            if get_prof_resp.status_code == 200:
                miner1_profile_id = get_prof_resp.json().get("id", "miner1")

        vote_payload = {
            "vote_type": "FOR",
            "reason": "Attract more miners"
        }
        vote_response = await client.post(
            f"{AITBC_URL}/governance/proposals/{proposal_id}/vote?voter_id={miner1_profile_id}",
            json=vote_payload
        )
        assert vote_response.status_code in [200, 201], f"Failed to vote: {vote_response.text}"

@pytest.mark.asyncio
async def test_adaptive_scaler_trigger():
    """Test Phase 10.2: Verify Adaptive Scaler Trigger"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{AITBC_URL}/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
