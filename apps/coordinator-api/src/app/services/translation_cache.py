"""
Translation cache service with optional HMAC integrity protection.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class TranslationCache:
    def __init__(self, cache_file: str = "translation_cache.json", hmac_key: str | None = None):
        self.cache_file = Path(cache_file)
        self.cache: dict[str, dict[str, Any]] = {}
        self.last_updated: datetime | None = None
        self.hmac_key = hmac_key.encode() if hmac_key else None
        self._load()

    def _load(self) -> None:
        if not self.cache_file.exists():
            return
        data = self.cache_file.read_bytes()
        if self.hmac_key:
            # Verify HMAC-SHA256(key || data)
            stored = json.loads(data)
            mac = bytes.fromhex(stored.pop("mac", ""))
            expected = hmac.new(self.hmac_key, json.dumps(stored, separators=(",", ":")).encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(mac, expected):
                raise ValueError("Translation cache HMAC verification failed")
            data = json.dumps(stored).encode()
        payload = json.loads(data)
        self.cache = payload.get("cache", {})
        last_iso = payload.get("last_updated")
        self.last_updated = datetime.fromisoformat(last_iso) if last_iso else None

    def _save(self) -> None:
        payload = {"cache": self.cache, "last_updated": (self.last_updated or datetime.now(UTC)).isoformat()}
        if self.hmac_key:
            raw = json.dumps(payload, separators=(",", ":")).encode()
            mac = hmac.new(self.hmac_key, raw, hashlib.sha256).digest()
            payload["mac"] = mac.hex()
        self.cache_file.write_text(json.dumps(payload, indent=2))

    def get(self, source_text: str, source_lang: str, target_lang: str) -> str | None:
        key = f"{source_lang}:{target_lang}:{source_text}"
        entry = self.cache.get(key)
        if not entry:
            return None
        return entry["translation"]

    def set(self, source_text: str, source_lang: str, target_lang: str, translation: str) -> None:
        key = f"{source_lang}:{target_lang}:{source_text}"
        self.cache[key] = {"translation": translation, "timestamp": datetime.now(UTC).isoformat()}
        self._save()

    def clear(self) -> None:
        self.cache.clear()
        self.last_updated = None
        if self.cache_file.exists():
            self.cache_file.unlink()

    def size(self) -> int:
        return len(self.cache)
