"""
Agent Communication Training Stage

Trains agents on effective communication patterns using the coordinator API.
Tests hierarchical, peer-to-peer, and broadcast protocols with metrics collection.
"""

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any

import aiohttp


class CommunicationTrainingStage:
    """Training stage for agent communication protocols"""

    def __init__(self, coordinator_url: str = "http://localhost:9001"):
        self.coordinator_url = coordinator_url
        self.metrics = {
            "total_messages_sent": 0,
            "successful_messages": 0,
            "failed_messages": 0,
            "hierarchical_success": 0,
            "hierarchical_total": 0,
            "peer_to_peer_success": 0,
            "peer_to_peer_total": 0,
            "broadcast_success": 0,
            "broadcast_total": 0,
            "avg_latency_ms": 0,
            "latency_samples": []
        }

    async def send_message(
        self,
        receiver_id: str,
        message_type: str,
        payload: dict[str, Any],
        protocol: str = "hierarchical",
        priority: str = "normal"
    ) -> dict[str, Any]:
        """Send a message via coordinator API"""
        start_time = time.time()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.coordinator_url}/messages/send",
                    json={
                        "receiver_id": receiver_id,
                        "message_type": message_type,
                        "payload": payload,
                        "priority": priority,
                        "protocol": protocol
                    }
                ) as response:
                    latency_ms = (time.time() - start_time) * 1000
                    self.metrics["latency_samples"].append(latency_ms)

                    if response.status == 200:
                        data = await response.json()
                        self.metrics["total_messages_sent"] += 1
                        self.metrics["successful_messages"] += 1

                        if protocol == "hierarchical":
                            self.metrics["hierarchical_success"] += 1
                            self.metrics["hierarchical_total"] += 1
                        elif protocol == "peer_to_peer":
                            self.metrics["peer_to_peer_success"] += 1
                            self.metrics["peer_to_peer_total"] += 1

                        return {"success": True, "data": data, "latency_ms": latency_ms}
                    else:
                        self.metrics["total_messages_sent"] += 1
                        self.metrics["failed_messages"] += 1

                        if protocol == "hierarchical":
                            self.metrics["hierarchical_total"] += 1
                        elif protocol == "peer_to_peer":
                            self.metrics["peer_to_peer_total"] += 1

                        error_text = await response.text()
                        return {"success": False, "error": error_text, "latency_ms": latency_ms}

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self.metrics["total_messages_sent"] += 1
            self.metrics["failed_messages"] += 1

            if protocol == "hierarchical":
                self.metrics["hierarchical_total"] += 1
            elif protocol == "peer_to_peer":
                self.metrics["peer_to_peer_total"] += 1

            return {"success": False, "error": str(e), "latency_ms": latency_ms}

    async def broadcast_message(
        self,
        message_type: str,
        payload: dict[str, Any],
        agent_type: str = None,
        capabilities: list[str] = None,
        priority: str = "normal"
    ) -> dict[str, Any]:
        """Broadcast a message to multiple agents"""
        start_time = time.time()

        try:
            async with aiohttp.ClientSession() as session:
                request_body = {
                    "message_type": message_type,
                    "payload": payload,
                    "priority": priority
                }

                if agent_type:
                    request_body["agent_type"] = agent_type
                if capabilities:
                    request_body["capabilities"] = capabilities

                async with session.post(
                    f"{self.coordinator_url}/messages/broadcast",
                    json=request_body
                ) as response:
                    latency_ms = (time.time() - start_time) * 1000
                    self.metrics["latency_samples"].append(latency_ms)

                    if response.status == 200:
                        data = await response.json()
                        self.metrics["total_messages_sent"] += data.get("count", 0)
                        self.metrics["successful_messages"] += data.get("count", 0)
                        self.metrics["broadcast_success"] += 1
                        self.metrics["broadcast_total"] += 1

                        return {"success": True, "data": data, "latency_ms": latency_ms}
                    else:
                        self.metrics["broadcast_total"] += 1
                        error_text = await response.text()
                        return {"success": False, "error": error_text, "latency_ms": latency_ms}

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self.metrics["broadcast_total"] += 1
            return {"success": False, "error": str(e), "latency_ms": latency_ms}

    async def get_message_history(
        self,
        sender_id: str = None,
        receiver_id: str = None,
        limit: int = 100
    ) -> dict[str, Any]:
        """Retrieve message history"""
        try:
            async with aiohttp.ClientSession() as session:
                params = {"limit": limit}
                if sender_id:
                    params["sender_id"] = sender_id
                if receiver_id:
                    params["receiver_id"] = receiver_id

                async with session.get(
                    f"{self.coordinator_url}/messages/history",
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    else:
                        error_text = await response.text()
                        return {"success": False, "error": error_text}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def add_peer(self, agent_id: str, peer_id: str) -> dict[str, Any]:
        """Add a peer connection"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.coordinator_url}/peers/add",
                    params={"agent_id": agent_id, "peer_id": peer_id}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    else:
                        error_text = await response.text()
                        return {"success": False, "error": error_text}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_peers(self, agent_id: str = None) -> dict[str, Any]:
        """Get peer connections"""
        try:
            async with aiohttp.ClientSession() as session:
                if agent_id:
                    url = f"{self.coordinator_url}/peers/{agent_id}"
                else:
                    url = f"{self.coordinator_url}/peers"

                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "data": data}
                    else:
                        error_text = await response.text()
                        return {"success": False, "error": error_text}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def calculate_metrics(self) -> dict[str, Any]:
        """Calculate final metrics"""
        if self.metrics["latency_samples"]:
            self.metrics["avg_latency_ms"] = sum(self.metrics["latency_samples"]) / len(self.metrics["latency_samples"])

        success_rate = 0
        if self.metrics["total_messages_sent"] > 0:
            success_rate = (self.metrics["successful_messages"] / self.metrics["total_messages_sent"]) * 100

        hierarchical_rate = 0
        if self.metrics["hierarchical_total"] > 0:
            hierarchical_rate = (self.metrics["hierarchical_success"] / self.metrics["hierarchical_total"]) * 100

        peer_to_peer_rate = 0
        if self.metrics["peer_to_peer_total"] > 0:
            peer_to_peer_rate = (self.metrics["peer_to_peer_success"] / self.metrics["peer_to_peer_total"]) * 100

        return {
            "total_messages_sent": self.metrics["total_messages_sent"],
            "successful_messages": self.metrics["successful_messages"],
            "failed_messages": self.metrics["failed_messages"],
            "overall_success_rate_percent": round(success_rate, 2),
            "hierarchical_protocol": {
                "total": self.metrics["hierarchical_total"],
                "successful": self.metrics["hierarchical_success"],
                "success_rate_percent": round(hierarchical_rate, 2)
            },
            "peer_to_peer_protocol": {
                "total": self.metrics["peer_to_peer_total"],
                "successful": self.metrics["peer_to_peer_success"],
                "success_rate_percent": round(peer_to_peer_rate, 2)
            },
            "broadcast_protocol": {
                "total": self.metrics["broadcast_total"],
                "successful": self.metrics["broadcast_success"],
                "success_rate_percent": round((self.metrics["broadcast_success"] / self.metrics["broadcast_total"] * 100) if self.metrics["broadcast_total"] > 0 else 0, 2)
            },
            "performance": {
                "avg_latency_ms": round(self.metrics["avg_latency_ms"], 2),
                "min_latency_ms": round(min(self.metrics["latency_samples"]) if self.metrics["latency_samples"] else 0, 2),
                "max_latency_ms": round(max(self.metrics["latency_samples"]) if self.metrics["latency_samples"] else 0, 2)
            }
        }


async def run_hierarchical_training(trainer: CommunicationTrainingStage, num_agents: int = 4):
    """Train hierarchical communication protocol"""
    print("\n=== Hierarchical Protocol Training ===")

    for i in range(10):
        agent_id = f"worker-{(i % num_agents) + 1}"
        result = await trainer.send_message(
            receiver_id=agent_id,
            message_type="direct",
            payload={"training_step": i, "task": f"hierarchical_task_{i}"},
            protocol="hierarchical"
        )

        if result["success"]:
            print(f"  Step {i}: Message sent to {agent_id} (latency: {result['latency_ms']:.2f}ms)")
        else:
            print(f"  Step {i}: Failed to send to {agent_id} - {result.get('error', 'Unknown error')}")

        await asyncio.sleep(0.1)


async def run_peer_to_peer_training(trainer: CommunicationTrainingStage, num_agents: int = 4):
    """Train peer-to-peer communication protocol"""
    print("\n=== Peer-to-Peer Protocol Training ===")

    # First ensure peer connections exist
    for i in range(num_agents):
        agent_id = f"worker-{i + 1}"
        peer_id = f"worker-{((i + 1) % num_agents) + 1}"
        await trainer.add_peer(agent_id, peer_id)

    for i in range(10):
        agent_id = f"worker-{(i % num_agents) + 1}"
        result = await trainer.send_message(
            receiver_id=agent_id,
            message_type="direct",
            payload={"training_step": i, "task": f"peer_to_peer_task_{i}"},
            protocol="peer_to_peer"
        )

        if result["success"]:
            print(f"  Step {i}: Message sent to {agent_id} (latency: {result['latency_ms']:.2f}ms)")
        else:
            print(f"  Step {i}: Failed to send to {agent_id} - {result.get('error', 'Unknown error')}")

        await asyncio.sleep(0.1)


async def run_broadcast_training(trainer: CommunicationTrainingStage):
    """Train broadcast communication protocol"""
    print("\n=== Broadcast Protocol Training ===")

    for i in range(5):
        result = await trainer.broadcast_message(
            message_type="broadcast",
            payload={"training_step": i, "announcement": f"broadcast_announcement_{i}"},
            agent_type="worker"
        )

        if result["success"]:
            data = result["data"]
            print(f"  Step {i}: Broadcast sent to {data['count']} agents (latency: {result['latency_ms']:.2f}ms)")
        else:
            print(f"  Step {i}: Failed to broadcast - {result.get('error', 'Unknown error')}")

        await asyncio.sleep(0.2)


async def main():
    """Main training execution"""
    print("=" * 60)
    print("Agent Communication Training Stage")
    print("=" * 60)
    print(f"Started at: {datetime.now(UTC).isoformat()}")

    trainer = CommunicationTrainingStage(coordinator_url="http://aitbc1:9001")

    # Run training scenarios
    await run_hierarchical_training(trainer)
    await run_peer_to_peer_training(trainer)
    await run_broadcast_training(trainer)

    # Get message history
    print("\n=== Message History Check ===")
    history = await trainer.get_message_history(limit=10)
    if history["success"]:
        print(f"  Retrieved {history['data']['count']} recent messages")
    else:
        print(f"  Failed to retrieve history - {history.get('error', 'Unknown error')}")

    # Get peer connections
    print("\n=== Peer Connections Check ===")
    peers = await trainer.get_peers()
    if peers["success"]:
        data = peers["data"]
        print(f"  Total agents with peers: {data['total_agents']}")
        print(f"  Total peer connections: {data['total_peers']}")
    else:
        print(f"  Failed to retrieve peers - {peers.get('error', 'Unknown error')}")

    # Calculate and display final metrics
    print("\n" + "=" * 60)
    print("Training Results")
    print("=" * 60)
    final_metrics = trainer.calculate_metrics()
    print(json.dumps(final_metrics, indent=2))

    print(f"\nCompleted at: {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
