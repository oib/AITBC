"""
Tests for agent-coordinator modules previously ignored by MyPy.

Targets the four biggest coverage gaps:
- prometheus_metrics.py
- message_encryption.py
- alerting.py
- message_storage.py
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

SRC_ROOT = Path("/opt/aitbc/apps/agent-coordinator/src")


def _load_module(module_name: str, rel_path: str):
    """Load a module directly from its file path to avoid app-namespace conflicts."""
    full_name = f"agent_coordinator_{module_name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = importlib.util.spec_from_file_location(
        full_name, SRC_ROOT / rel_path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load prometheus_metrics module
_pm = _load_module("prometheus_metrics", "app/monitoring/prometheus_metrics.py")
Counter = _pm.Counter
Gauge = _pm.Gauge
Histogram = _pm.Histogram
MetricValue = _pm.MetricValue
MetricsRegistry = _pm.MetricsRegistry
PerformanceMonitor = _pm.PerformanceMonitor

# Load message_encryption module
_enc = _load_module("message_encryption", "app/encryption/message_encryption.py")
AgentKeyPair = _enc.AgentKeyPair
EncryptedMessage = _enc.EncryptedMessage
MessageEncryptor = _enc.MessageEncryptor
get_encryptor = _enc.get_encryptor

# Load alerting module
_alert = _load_module("alerting", "app/monitoring/alerting.py")
Alert = _alert.Alert
AlertManager = _alert.AlertManager
AlertRule = _alert.AlertRule
AlertSeverity = _alert.AlertSeverity
AlertStatus = _alert.AlertStatus
NotificationChannel = _alert.NotificationChannel
NotificationManager = _alert.NotificationManager
SLAMonitor = _alert.SLAMonitor

# Load message_storage module
_storage = _load_module("message_storage", "app/storage/message_storage.py")
MessageStorage = _storage.MessageStorage
PeerStorage = _storage.PeerStorage


# ---------------------------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------------------------

class TestCounter:
    def test_counter_basic(self):
        c = Counter("test_counter", "A test counter", ["method"])
        c.inc(1.0, method="GET")
        c.inc(2.0, method="GET")
        c.inc(1.0, method="POST")
        assert c.get_value(method="GET") == 3.0
        assert c.get_value(method="POST") == 1.0
        assert c.get_value(method="DELETE") == 0.0

    def test_counter_reset(self):
        c = Counter("test", "desc")
        c.inc(5.0)
        assert c.get_value() == 5.0
        c.reset()
        assert c.get_value() == 0.0
        c.reset_all()
        assert c.get_all_values() == {}

    def test_counter_no_labels(self):
        c = Counter("test", "desc")
        c.inc(3.0)
        assert c.get_value() == 3.0


class TestGauge:
    def test_gauge_basic(self):
        g = Gauge("test_gauge", "A test gauge", ["status"])
        g.set(10.0, status="active")
        g.inc(5.0, status="active")
        g.dec(2.0, status="active")
        assert g.get_value(status="active") == 13.0
        g.set(0.0, status="active")
        assert g.get_value(status="active") == 0.0

    def test_gauge_all_values(self):
        g = Gauge("test", "desc")
        g.set(1.0)
        g.set(2.0)
        assert g.get_all_values() == {"_default": 2.0}


class TestHistogram:
    def test_histogram_observe(self):
        h = Histogram("test_hist", "A test histogram")
        h.observe(0.01)
        h.observe(0.1)
        h.observe(5.0)
        assert h.get_count() == 3
        assert h.get_sum() == pytest.approx(5.11)
        buckets = h.get_bucket_counts()
        assert buckets["inf"] == 3

    def test_histogram_with_labels(self):
        h = Histogram("test", "desc", labels=["endpoint"])
        h.observe(0.5, endpoint="/api")
        assert h.get_count(endpoint="/api") == 1


class TestMetricsRegistry:
    def test_registry_create_metrics(self):
        reg = MetricsRegistry()
        c = reg.counter("requests", "Total requests")
        g = reg.gauge("active", "Active connections")
        h = reg.histogram("duration", "Request duration")
        c.inc()
        g.set(5.0)
        h.observe(0.5)
        metrics = reg.get_all_metrics()
        assert "requests" in metrics
        assert "active" in metrics
        assert "duration" in metrics

    def test_registry_reset_all(self):
        reg = MetricsRegistry()
        c = reg.counter("c", "desc")
        c.inc(10.0)
        reg.reset_all()
        assert c.get_value() == 0.0


class TestPerformanceMonitor:
    def test_initialization(self):
        reg = MetricsRegistry()
        pm = PerformanceMonitor(reg)
        assert pm.registry is reg
        assert len(pm.error_counts) == 0

    def test_update_system_metrics(self):
        reg = MetricsRegistry()
        pm = PerformanceMonitor(reg)
        pm.update_system_metrics(1024 * 1024 * 100, 50.0)
        g = reg.gauge("system_memory_usage_bytes", "Memory usage in bytes")
        assert g.get_value() == 1024 * 1024 * 100

    def test_record_request_error(self):
        reg = MetricsRegistry()
        pm = PerformanceMonitor(reg)
        pm.record_request("GET", "/api", 500, 0.1)
        assert pm.error_counts["GET_/api"] == 1


# ---------------------------------------------------------------------------
# Message Encryption
# ---------------------------------------------------------------------------

class TestEncryptedMessage:
    def test_to_dict_from_dict(self):
        msg = EncryptedMessage(
            ciphertext=b"cipher",
            session_key=b"key",
            nonce=b"nonce",
            signature=b"sig",
            sender_id="agent-1",
        )
        d = msg.to_dict()
        assert d["sender_id"] == "agent-1"
        restored = EncryptedMessage.from_dict(d)
        assert restored.ciphertext == b"cipher"
        assert restored.sender_id == "agent-1"


class TestAgentKeyPair:
    def test_to_dict_from_dict_with_private(self):
        kp = AgentKeyPair(
            agent_id="agent-1",
            public_key=b"pub",
            private_key=b"priv",
            key_id="key-1",
        )
        d = kp.to_dict()
        assert "private_key" in d
        restored = AgentKeyPair.from_dict(d)
        assert restored.private_key == b"priv"

    def test_to_dict_without_private(self):
        kp = AgentKeyPair(agent_id="agent-1", public_key=b"pub")
        d = kp.to_dict()
        assert "private_key" not in d
        restored = AgentKeyPair.from_dict(d)
        assert restored.private_key is None


class TestMessageEncryptor:
    def test_generate_and_get_key(self, tmp_path):
        encryptor = MessageEncryptor(keys_dir=str(tmp_path))
        kp = encryptor.generate_key_pair("agent-1")
        assert kp.agent_id == "agent-1"
        assert encryptor.get_public_key("agent-1") == kp.public_key

    def test_register_public_key(self, tmp_path):
        encryptor = MessageEncryptor(keys_dir=str(tmp_path))
        kp = encryptor.generate_key_pair("agent-1")
        success = encryptor.register_public_key("agent-2", kp.public_key)
        assert success is True
        assert encryptor.get_public_key("agent-2") == kp.public_key

    def test_encrypt_decrypt_roundtrip(self, tmp_path):
        encryptor = MessageEncryptor(keys_dir=str(tmp_path))
        encryptor.generate_key_pair("sender")
        encryptor.generate_key_pair("recipient")
        message = {"action": "heartbeat", "data": {"status": "ok"}}
        encrypted = encryptor.encrypt_message(message, "sender", "recipient")
        assert encrypted is not None
        decrypted = encryptor.decrypt_message(encrypted, "recipient")
        assert decrypted == message

    def test_encrypt_missing_recipient(self, tmp_path):
        encryptor = MessageEncryptor(keys_dir=str(tmp_path))
        encryptor.generate_key_pair("sender")
        result = encryptor.encrypt_message({}, "sender", "unknown")
        assert result is None

    def test_decrypt_missing_private_key(self, tmp_path):
        encryptor = MessageEncryptor(keys_dir=str(tmp_path))
        encryptor.generate_key_pair("sender")
        encryptor.register_public_key("recipient", encryptor.generate_key_pair("other").public_key)
        message = {"test": "data"}
        encrypted = encryptor.encrypt_message(message, "sender", "other")
        result = encryptor.decrypt_message(encrypted, "recipient")
        assert result is None

    def test_verify_signature(self, tmp_path):
        encryptor = MessageEncryptor(keys_dir=str(tmp_path))
        encryptor.generate_key_pair("sender")
        encryptor.generate_key_pair("recipient")
        encrypted = encryptor.encrypt_message({"msg": "hi"}, "sender", "recipient")
        assert encryptor.verify_signature(encrypted, "sender") is True
        assert encryptor.verify_signature(encrypted, "unknown") is False

    def test_rotate_key_pair(self, tmp_path):
        import time
        encryptor = MessageEncryptor(keys_dir=str(tmp_path))
        old = encryptor.generate_key_pair("agent-1")
        time.sleep(1.1)
        new = encryptor.rotate_key_pair("agent-1")
        assert new is not None
        assert new.key_id != old.key_id

    def test_rotate_nonexistent(self, tmp_path):
        encryptor = MessageEncryptor(keys_dir=str(tmp_path))
        assert encryptor.rotate_key_pair("agent-x") is None

    def test_get_encryptor_singleton(self, tmp_path):
        with patch("agent_coordinator_message_encryption._encryptor", None):
            e1 = get_encryptor()
            e2 = get_encryptor()
            assert e1 is e2


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------

class TestAlert:
    def test_to_dict(self):
        from datetime import UTC, datetime
        alert = Alert(
            alert_id="a1",
            name="Test Alert",
            description="Something is wrong",
            severity=AlertSeverity.WARNING,
            status=AlertStatus.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            labels={"env": "test"},
        )
        d = alert.to_dict()
        assert d["name"] == "Test Alert"
        assert d["severity"] == "warning"


class TestAlertRule:
    def test_to_dict(self):
        from datetime import timedelta
        rule = AlertRule(
            rule_id="r1",
            name="High CPU",
            description="CPU > 80%",
            severity=AlertSeverity.CRITICAL,
            condition="cpu_usage > threshold",
            threshold=80.0,
            duration=timedelta(minutes=5),
            notification_channels=[NotificationChannel.LOG],
        )
        d = rule.to_dict()
        assert d["name"] == "High CPU"
        assert d["threshold"] == 80.0
        assert d["notification_channels"] == ["log"]


class TestSLAMonitor:
    def test_add_rule_and_record(self):
        from datetime import timedelta
        sla = SLAMonitor()
        sla.add_sla_rule("sla1", "Availability", 99.9, timedelta(hours=1), "availability")
        sla.record_metric("sla1", 99.95)
        sla.record_metric("sla1", 99.8)
        result = sla.get_sla_compliance("sla1")
        assert result["status"] == "success"
        assert result["total_measurements"] == 2
        assert result["violations_count"] == 1

    def test_get_sla_not_found(self):
        assert SLAMonitor().get_sla_compliance("missing")["status"] == "error"

    def test_get_all_sla_status(self):
        from datetime import timedelta
        sla = SLAMonitor()
        sla.add_sla_rule("sla1", "Availability", 99.9, timedelta(hours=1), "availability")
        result = sla.get_all_sla_status()
        assert result["status"] == "success"
        assert result["total_slas"] == 1
        assert result["overall_compliance"] == 100.0

    def test_record_metric_no_timestamp(self):
        from datetime import timedelta
        sla = SLAMonitor()
        sla.add_sla_rule("sla1", "Availability", 99.9, timedelta(hours=1), "availability")
        sla.record_metric("sla1", 99.0)
        result = sla.get_sla_compliance("sla1")
        assert result["compliance_percentage"] == 100.0

    def test_cleanup_old_metrics(self):
        from datetime import UTC, datetime, timedelta
        sla = SLAMonitor()
        window = timedelta(seconds=1)
        sla.add_sla_rule("sla1", "Latency", 100.0, window, "latency")
        old_ts = datetime.now(UTC) - timedelta(seconds=10)
        sla.record_metric("sla1", 50.0, timestamp=old_ts)
        new_ts = datetime.now(UTC)
        sla.record_metric("sla1", 200.0, timestamp=new_ts)
        result = sla.get_sla_compliance("sla1")
        assert result["total_measurements"] == 1


class TestNotificationManager:
    def test_configure_channels(self):
        nm = NotificationManager()
        nm.configure_email("smtp.example.com", 587, "user", "pass", "from@example.com")
        assert nm.email_config["smtp_server"] == "smtp.example.com"
        nm.configure_slack("https://hooks.slack.com/test", "#alerts")
        assert nm.slack_config["channel"] == "#alerts"
        nm.add_webhook("primary", "https://webhook.example.com")
        assert "primary" in nm.webhook_configs

    @pytest.mark.asyncio
    async def test_send_log_notification(self):
        from datetime import UTC, datetime
        nm = NotificationManager()
        alert = Alert(
            alert_id="a1", name="Test", description="Desc",
            severity=AlertSeverity.INFO, status=AlertStatus.ACTIVE,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        nm._send_log(alert, "message")

    @pytest.mark.asyncio
    async def test_send_email_not_configured(self):
        from datetime import UTC, datetime
        nm = NotificationManager()
        alert = Alert(
            alert_id="a1", name="Test", description="Desc",
            severity=AlertSeverity.INFO, status=AlertStatus.ACTIVE,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        await nm._send_email(alert, "msg")

    @pytest.mark.asyncio
    async def test_send_slack_not_configured(self):
        from datetime import UTC, datetime
        nm = NotificationManager()
        alert = Alert(
            alert_id="a1", name="Test", description="Desc",
            severity=AlertSeverity.INFO, status=AlertStatus.ACTIVE,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        await nm._send_slack(alert, "msg")

    @pytest.mark.asyncio
    async def test_send_slack_success(self):
        from datetime import UTC, datetime
        nm = NotificationManager()
        nm.configure_slack("https://hooks.slack.com/test", "#alerts")
        alert = Alert(
            alert_id="a1", name="Test", description="Desc",
            severity=AlertSeverity.CRITICAL, status=AlertStatus.ACTIVE,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        with patch("requests.post") as mock_post:
            mock_post.return_value.raise_for_status = lambda: None
            await nm._send_slack(alert, "msg")
            assert mock_post.called

    @pytest.mark.asyncio
    async def test_send_webhook(self):
        from datetime import UTC, datetime
        nm = NotificationManager()
        nm.add_webhook("primary", "https://webhook.example.com")
        alert = Alert(
            alert_id="a1", name="Test", description="Desc",
            severity=AlertSeverity.INFO, status=AlertStatus.ACTIVE,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        with patch("requests.post") as mock_post:
            mock_post.return_value.raise_for_status = lambda: None
            await nm._send_webhook(alert, "msg")
            assert mock_post.called


class TestAlertManager:
    def test_initialization(self):
        am = AlertManager()
        assert len(am.rules) > 0
        assert "high_error_rate" in am.rules

    def test_add_remove_rule(self):
        from datetime import timedelta
        am = AlertManager()
        rule = AlertRule(
            rule_id="custom", name="Custom", description="Desc",
            severity=AlertSeverity.WARNING, condition="test", threshold=1.0,
            duration=timedelta(minutes=1),
        )
        am.add_rule(rule)
        assert "custom" in am.rules
        am.remove_rule("custom")
        assert "custom" not in am.rules

    def test_evaluate_rules_no_trigger(self):
        am = AlertManager()
        am.evaluate_rules({"error_rate": 0.0, "avg_response_time": 0.0, "active_agents": 10})
        assert len(am.active_conditions) == 0

    def test_evaluate_rules_triggers(self):
        am = AlertManager()
        am.evaluate_rules({"error_rate": 0.1})
        assert "high_error_rate" in am.active_conditions

    def test_trigger_and_resolve(self):
        from datetime import UTC, datetime, timedelta
        am = AlertManager()
        am.active_conditions["high_error_rate"] = datetime.now(UTC) - timedelta(minutes=10)
        am.evaluate_rules({"error_rate": 0.1})
        active = am.get_active_alerts()
        assert len(active) == 1
        alert_id = active[0]["alert_id"]
        result = am.resolve_alert(alert_id)
        assert result["status"] == "success"
        assert len(am.get_active_alerts()) == 0

    def test_resolve_nonexistent(self):
        assert AlertManager().resolve_alert("missing")["status"] == "error"

    def test_get_alert_history(self):
        from datetime import UTC, datetime, timedelta
        am = AlertManager()
        am.active_conditions["high_error_rate"] = datetime.now(UTC) - timedelta(minutes=10)
        am.evaluate_rules({"error_rate": 0.1})
        history = am.get_alert_history(limit=10)
        assert len(history) > 0

    def test_get_alert_stats(self):
        am = AlertManager()
        stats = am.get_alert_stats()
        assert "total_rules" in stats
        assert stats["total_alerts"] == 0

    def test_alert_stats_with_active(self):
        from datetime import UTC, datetime, timedelta
        am = AlertManager()
        am.active_conditions["high_error_rate"] = datetime.now(UTC) - timedelta(minutes=10)
        am.evaluate_rules({"error_rate": 0.1})
        stats = am.get_alert_stats()
        assert stats["active_alerts"] >= 1

    def test_no_duplicate_active_alerts(self):
        from datetime import UTC, datetime, timedelta
        am = AlertManager()
        am.active_conditions["high_error_rate"] = datetime.now(UTC) - timedelta(minutes=10)
        am.evaluate_rules({"error_rate": 0.1})
        am.evaluate_rules({"error_rate": 0.1})
        assert len(am.get_active_alerts()) == 1

    def test_evaluate_disabled_rule(self):
        am = AlertManager()
        am.rules["high_error_rate"].enabled = False
        am.evaluate_rules({"error_rate": 0.1})
        assert "high_error_rate" not in am.active_conditions

    def test_evaluate_all_conditions(self):
        from datetime import UTC, datetime, timedelta
        am = AlertManager()
        past = datetime.now(UTC) - timedelta(minutes=10)
        metrics = {
            "error_rate": 0.1,
            "avg_response_time": 3.0,
            "active_agents": 1,
            "memory_usage_percent": 0.9,
            "cpu_usage_percent": 0.9,
        }
        for rule_id in list(am.rules.keys()):
            am.active_conditions[rule_id] = past
        am.evaluate_rules(metrics)
        assert len(am.get_active_alerts()) > 0


# ---------------------------------------------------------------------------
# Message Storage
# ---------------------------------------------------------------------------

class TestMessageStorage:
    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.hset = AsyncMock(return_value=1)
        redis.sadd = AsyncMock(return_value=1)
        redis.zadd = AsyncMock(return_value=1)
        redis.zcard = AsyncMock(return_value=5)
        redis.hgetall = AsyncMock(side_effect=lambda *a, **k: {"sender": "a1", "payload": '{"data": 1}'})
        redis.smembers = AsyncMock(return_value=["msg1", "msg2"])
        redis.zrevrange = AsyncMock(return_value=["msg1", "msg2"])
        redis.srem = AsyncMock(return_value=1)
        redis.zrem = AsyncMock(return_value=1)
        redis.delete = AsyncMock(return_value=1)
        redis.close = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_start_stop(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        with patch("redis.asyncio.from_url", AsyncMock(return_value=mock_redis)):
            await storage.start()
            assert storage.redis is not None
            await storage.stop()

    @pytest.mark.asyncio
    async def test_store_message(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        from datetime import UTC, datetime
        result = await storage.store_message("msg1", {
            "sender": "a1", "recipient": "a2", "timestamp": datetime.now(UTC).isoformat()
        })
        assert result is True

    @pytest.mark.asyncio
    async def test_store_message_error(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        mock_redis.hset = AsyncMock(side_effect=Exception("Redis error"))
        storage.redis = mock_redis
        result = await storage.store_message("msg1", {"sender": "a1"})
        assert result is False

    @pytest.mark.asyncio
    async def test_get_message_count(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        count = await storage.get_message_count()
        assert count == 5

    @pytest.mark.asyncio
    async def test_get_message(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        msg = await storage.get_message("msg1")
        assert msg is not None
        assert msg["payload"] == {"data": 1}

    @pytest.mark.asyncio
    async def test_get_message_error(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        mock_redis.hgetall = AsyncMock(side_effect=Exception("Redis error"))
        storage.redis = mock_redis
        msg = await storage.get_message("msg1")
        assert msg is None

    @pytest.mark.asyncio
    async def test_get_messages_by_sender(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        msgs = await storage.get_messages_by_sender("a1", limit=10)
        assert len(msgs) == 2

    @pytest.mark.asyncio
    async def test_get_messages_by_receiver(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        msgs = await storage.get_messages_by_receiver("a2", limit=10)
        assert len(msgs) == 2

    @pytest.mark.asyncio
    async def test_get_all_messages(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        msgs = await storage.get_all_messages(limit=10)
        assert len(msgs) == 2

    @pytest.mark.asyncio
    async def test_delete_message(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        result = await storage.delete_message("msg1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_message_not_found(self, mock_redis):
        storage = MessageStorage("redis://localhost:6379/0")
        mock_redis.hgetall = AsyncMock(return_value={})
        storage.redis = mock_redis
        result = await storage.delete_message("msg1")
        assert result is False


class TestPeerStorage:
    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.sadd = AsyncMock(return_value=1)
        redis.srem = AsyncMock(return_value=1)
        redis.delete = AsyncMock(return_value=1)
        redis.smembers = AsyncMock(return_value=["peer1", "peer2"])
        redis.hgetall = AsyncMock(return_value={"ip": "127.0.0.1"})
        redis.keys = AsyncMock(return_value=["peers:agent1", "peers:agent2"])
        redis.close = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_start_stop(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        with patch("redis.asyncio.from_url", AsyncMock(return_value=mock_redis)):
            await storage.start()
            assert storage.redis is not None
            await storage.stop()

    @pytest.mark.asyncio
    async def test_add_peer(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        result = await storage.add_peer("agent1", "peer1", {"role": "worker"})
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_peer(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        result = await storage.remove_peer("agent1", "peer1")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_agent_peers(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        peers = await storage.get_agent_peers("agent1")
        assert peers == ["peer1", "peer2"]

    @pytest.mark.asyncio
    async def test_get_peer_metadata(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        meta = await storage.get_peer_metadata("agent1", "peer1")
        assert meta == {"ip": "127.0.0.1"}

    @pytest.mark.asyncio
    async def test_get_all_peer_connections(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        storage.redis = mock_redis
        connections = await storage.get_all_peer_connections()
        assert "agent1" in connections
        assert "agent2" in connections

    @pytest.mark.asyncio
    async def test_add_peer_error(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        mock_redis.sadd = AsyncMock(side_effect=Exception("Redis error"))
        storage.redis = mock_redis
        result = await storage.add_peer("agent1", "peer1")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_peer_error(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        mock_redis.srem = AsyncMock(side_effect=Exception("Redis error"))
        storage.redis = mock_redis
        result = await storage.remove_peer("agent1", "peer1")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_agent_peers_error(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        mock_redis.smembers = AsyncMock(side_effect=Exception("Redis error"))
        storage.redis = mock_redis
        peers = await storage.get_agent_peers("agent1")
        assert peers == []

    @pytest.mark.asyncio
    async def test_get_all_peer_connections_error(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        mock_redis.keys = AsyncMock(side_effect=Exception("Redis error"))
        storage.redis = mock_redis
        result = await storage.get_all_peer_connections()
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_peer_metadata_none(self, mock_redis):
        storage = PeerStorage("redis://localhost:6379/0")
        mock_redis.hgetall = AsyncMock(return_value={})
        storage.redis = mock_redis
        meta = await storage.get_peer_metadata("agent1", "peer1")
        assert meta is None
