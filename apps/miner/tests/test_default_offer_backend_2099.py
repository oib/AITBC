"""#2099: default whisper/ffmpeg offers are published only while their backend is up.

Fleet reality (#1549): aitbc-whisper / aitbc-ffmpeg are not deployed on the
shop node, yet the miner published active offers for them every cycle.
"""

from unittest.mock import Mock, patch

import production_miner
import pytest
import requests

_OFFERS = [
    {"service_type": "whisper", "model": "base", "price": "0.02", "unit": "per_audio_min", "description": "w"},
    {"service_type": "ffmpeg", "model": "h264-transcode", "price": "0.005", "unit": "per_hour", "description": "f"},
    {"service_type": "ipfs", "model": "ipfs-host", "price": "0.01", "unit": "per_day", "description": "i"},
]


def _types(mock_run):
    return [c.args[0][c.args[0].index("--service-type") + 1] for c in mock_run.call_args_list]


class TestProbe:
    def test_unregistered_service_type_is_not_gated(self):
        assert production_miner._offer_backend_up("ollama") is True
        assert production_miner._offer_backend_up("ipfs") is True

    def test_healthy_backend(self, monkeypatch):
        monkeypatch.setenv("WHISPER_SERVICE_URL", "http://w:1/")
        with patch("production_miner.requests.get", return_value=Mock(status_code=200)) as get:
            assert production_miner._offer_backend_up("whisper") is True
        assert get.call_args.args[0] == "http://w:1/health"

    def test_non_200_is_down(self):
        with patch("production_miner.requests.get", return_value=Mock(status_code=503)):
            assert production_miner._offer_backend_up("ffmpeg") is False

    def test_connection_refused_is_down(self):
        with patch("production_miner.requests.get", side_effect=requests.exceptions.ConnectionError("refused")):
            assert production_miner._offer_backend_up("whisper") is False


class TestPublishGate:
    @pytest.mark.unit
    @patch("production_miner.subprocess.run")
    def test_down_backends_publish_nothing_but_ungated_offers_still_do(self, mock_run, monkeypatch, caplog):
        monkeypatch.setattr(production_miner, "DEFAULT_SOFTWARE_OFFERS", _OFFERS)
        mock_run.return_value = Mock(returncode=0, stdout="identical active offer exists, skipping", stderr="")
        with patch("production_miner.requests.get", side_effect=requests.exceptions.ConnectionError("x")):
            with caplog.at_level("WARNING", logger="production_miner"):
                production_miner.publish_default_offers([])
        assert _types(mock_run) == ["ipfs"]
        assert "Skipping default offer whisper/base: backend not reachable" in caplog.text
        assert "Skipping default offer ffmpeg/h264-transcode: backend not reachable" in caplog.text

    @pytest.mark.unit
    @patch("production_miner.subprocess.run")
    def test_skipped_offer_does_not_consume_the_nonce_slot(self, mock_run, monkeypatch):
        """whisper is down, ffmpeg is up: ffmpeg publishes in the same cycle."""
        monkeypatch.setattr(production_miner, "DEFAULT_SOFTWARE_OFFERS", _OFFERS[:2])
        mock_run.return_value = Mock(returncode=0, stdout="offer published tx=0x1", stderr="")

        def get(url, timeout):
            if ":8110" in url:
                raise requests.exceptions.ConnectionError("down")
            return Mock(status_code=200)

        with patch("production_miner.requests.get", side_effect=get):
            production_miner.publish_default_offers([])
        assert _types(mock_run) == ["ffmpeg"]

    @pytest.mark.unit
    @patch("production_miner.subprocess.run")
    def test_up_backends_publish_as_before(self, mock_run, monkeypatch):
        monkeypatch.setattr(production_miner, "DEFAULT_SOFTWARE_OFFERS", _OFFERS[:1])
        mock_run.return_value = Mock(returncode=0, stdout="offer published tx=0x1", stderr="")
        with patch("production_miner.requests.get", return_value=Mock(status_code=200)):
            production_miner.publish_default_offers([])
        assert _types(mock_run) == ["whisper"]
