from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

RoleResolver = Callable[[Any], Awaitable[Iterable[str] | str | None] | Iterable[str] | str | None]


@dataclass(slots=True)
class SceneRuntime:
    role_resolver: RoleResolver | None = None
    default_home: str | None = None
    home_by_role: dict[str, str] = field(default_factory=dict)


RUNTIME = SceneRuntime()
