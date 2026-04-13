from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_SAFE_TOKEN = re.compile(r"[^a-z0-9]+")


def _slug(value: str, *, limit: int = 12) -> str:
    normalized = _SAFE_TOKEN.sub("-", value.lower()).strip("-")
    return normalized[:limit] or "cb"


@dataclass(slots=True, frozen=True)
class CallbackNamespace:
    scope: str
    salt: str = "scenegram"

    def callback_prefix(self, name: str) -> str:
        digest = hashlib.sha1(f"{self.salt}:{self.scope}".encode()).hexdigest()[:8]
        return f"sg{digest}:{_slug(name)}"


def cb_namespace(scope: str, *, salt: str = "scenegram") -> CallbackNamespace:
    return CallbackNamespace(scope=scope, salt=salt)


__all__ = ["CallbackNamespace", "cb_namespace"]
