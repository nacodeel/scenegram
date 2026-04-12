from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class SceneRole(StrEnum):
    ANY = "any"
    USER = "user"
    MANAGER = "manager"
    ADMIN = "admin"


def normalize_role(role: SceneRole | str) -> str:
    return role.value if isinstance(role, SceneRole) else str(role)


def normalize_roles(roles: Iterable[SceneRole | str] | None) -> frozenset[str]:
    if not roles:
        return frozenset()
    return frozenset(normalize_role(role) for role in roles)
