from __future__ import annotations

from scenegram import AppScene, SceneRole


class ManagerScene(AppScene, state="manager.dashboard"):
    __abstract__ = False
    roles = frozenset({SceneRole.MANAGER.value})
    home_for_roles = frozenset({SceneRole.MANAGER.value})
