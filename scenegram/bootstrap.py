from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from aiogram import Router
from aiogram.filters import Command, Filter
from aiogram.fsm.scene import SceneRegistry

from .contracts import SceneCleanup, SceneModule
from .di import adapt_container
from .roles import SceneRole, normalize_role, normalize_roles
from .runtime import DEFAULT_CLEANUP, RUNTIME, RoleResolver


@dataclass(slots=True)
class EntryPoint:
    observer: str
    filters: tuple[Any, ...] = ()
    handler_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SceneDescriptor:
    state: str
    scene: type
    module: str
    roles: frozenset[str]
    home_scene: str | None
    home_for_roles: frozenset[str]
    entrypoints: tuple[EntryPoint, ...]
    scene_module: str | None = None


@dataclass(slots=True)
class SceneBootstrapResult:
    router: Router
    registry: SceneRegistry
    scenes: list[type]
    descriptors: list[SceneDescriptor]
    scene_map: dict[str, type]
    modules: dict[str, SceneModule]


class RoleAllowed(Filter):
    def __init__(
        self,
        role_resolver: RoleResolver,
        allowed_roles: Iterable[SceneRole | str],
    ) -> None:
        self.role_resolver = role_resolver
        self.allowed_roles = normalize_roles(allowed_roles)

    async def __call__(self, event: Any, **_: Any) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            message = getattr(event, "message", None)
            user = getattr(message, "from_user", None)

        if user is None:
            return False

        resolved = self.role_resolver(event)
        if inspect.isawaitable(resolved):
            resolved = await resolved

        if resolved is None:
            return False

        if isinstance(resolved, str):
            roles = {normalize_role(resolved)}
        else:
            roles = {normalize_role(role) for role in resolved}

        return bool(roles & self.allowed_roles)


def message_entry(*filters: Any, **handler_kwargs: Any) -> EntryPoint:
    return EntryPoint(
        observer="message",
        filters=tuple(filters),
        handler_kwargs=dict(handler_kwargs),
    )


def command_entry(*commands: str, **handler_kwargs: Any) -> EntryPoint:
    if not commands:
        raise ValueError("At least one command is required")
    return message_entry(Command(*commands), **handler_kwargs)


def callback_entry(*filters: Any, **handler_kwargs: Any) -> EntryPoint:
    return EntryPoint(
        observer="callback_query",
        filters=tuple(filters),
        handler_kwargs=dict(handler_kwargs),
    )


def _apply_filters(router: Router, *filters: Any) -> None:
    for observer_name in ("message", "callback_query"):
        observer = getattr(router, observer_name, None)
        if observer is not None and hasattr(observer, "filter"):
            observer.filter(*filters)


def _normalize_packages(package_name: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(package_name, str):
        return (package_name,)
    if not package_name:
        raise ValueError("At least one package name must be provided")
    return tuple(package_name)


def _discover_modules(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    module_names = [package.__name__]

    package_path = getattr(package, "__path__", None)
    if not package_path:
        return module_names

    for module_info in pkgutil.walk_packages(package_path, prefix=f"{package.__name__}."):
        module_names.append(module_info.name)

    return module_names


def discover_scene_modules(
    package_name: str | Sequence[str],
    *,
    extra_modules: Sequence[SceneModule] | None = None,
) -> dict[str, SceneModule]:
    discovered: dict[str, SceneModule] = {}

    for root_package in _normalize_packages(package_name):
        for module_name in _discover_modules(root_package):
            module = importlib.import_module(module_name)
            candidate = getattr(module, "SCENEGRAM_MODULE", None)
            if isinstance(candidate, SceneModule):
                discovered[candidate.name] = candidate

    for module in extra_modules or ():
        discovered[module.name] = module

    return discovered


def _match_scene_module(scene_cls: type, modules: Mapping[str, SceneModule]) -> str | None:
    explicit = getattr(scene_cls, "scene_module", None)
    if explicit:
        return explicit

    matched_name: str | None = None
    matched_length = -1
    module_name = scene_cls.__module__

    for scene_module in modules.values():
        prefix = scene_module.package_name
        if module_name == prefix or module_name.startswith(f"{prefix}."):
            if len(prefix) > matched_length:
                matched_name = scene_module.name
                matched_length = len(prefix)

    return matched_name


def discover_scene_descriptors(
    package_name: str | Sequence[str],
    base_scene_cls: type,
    *,
    modules: Mapping[str, SceneModule] | None = None,
) -> list[SceneDescriptor]:
    descriptors: dict[str, SceneDescriptor] = {}
    modules = modules or {}

    for root_package in _normalize_packages(package_name):
        for module_name in _discover_modules(root_package):
            module = importlib.import_module(module_name)

            for _, candidate in inspect.getmembers(module, inspect.isclass):
                if candidate is base_scene_cls:
                    continue
                if not issubclass(candidate, base_scene_cls):
                    continue
                if getattr(candidate, "__abstract__", False):
                    continue
                if candidate.__module__ != module.__name__:
                    continue

                scene_config = getattr(candidate, "__scene_config__", None)
                state = getattr(scene_config, "state", None)
                if not state:
                    continue

                scene_module = _match_scene_module(candidate, modules)

                descriptors[state] = SceneDescriptor(
                    state=state,
                    scene=candidate,
                    module=module.__name__,
                    roles=normalize_roles(getattr(candidate, "roles", {SceneRole.ANY.value})),
                    home_scene=getattr(candidate, "home_scene", None),
                    home_for_roles=normalize_roles(getattr(candidate, "home_for_roles", set())),
                    entrypoints=tuple(getattr(candidate, "entrypoints", ())),
                    scene_module=scene_module,
                )

    return [descriptors[state] for state in sorted(descriptors)]


def discover_scene_classes(
    package_name: str | Sequence[str],
    base_scene_cls: type,
    *,
    modules: Mapping[str, SceneModule] | None = None,
) -> list[type]:
    descriptors = discover_scene_descriptors(package_name, base_scene_cls, modules=modules)
    return [descriptor.scene for descriptor in descriptors]


def create_scenes_router(
    package_name: str | Sequence[str] = "scenes.modules",
    *,
    role_resolver: RoleResolver | None = None,
    default_home: str | None = None,
    base_scene_cls: type | None = None,
    service_container: Any | None = None,
    scene_modules: Sequence[SceneModule] | None = None,
    cleanup: SceneCleanup | None = None,
) -> SceneBootstrapResult:
    from .base import AppScene

    base_scene_cls = base_scene_cls or AppScene
    root_router = Router(name="scenes")
    registry = SceneRegistry(root_router, register_on_add=False)

    discovered_modules = discover_scene_modules(package_name, extra_modules=scene_modules)
    descriptors = discover_scene_descriptors(
        package_name,
        base_scene_cls,
        modules=discovered_modules,
    )
    scenes = [descriptor.scene for descriptor in descriptors]

    RUNTIME.reset()
    RUNTIME.role_resolver = role_resolver
    RUNTIME.default_home = default_home
    RUNTIME.service_container = adapt_container(service_container)
    RUNTIME.cleanup = cleanup or DEFAULT_CLEANUP
    RUNTIME.register_modules(discovered_modules.values())

    grouped_routers: dict[tuple[str, ...], Router] = {}

    for descriptor in descriptors:
        scene_cls = descriptor.scene
        allowed_roles = descriptor.roles

        RUNTIME.bind_scene_module(descriptor.state, descriptor.scene_module)

        for role in descriptor.home_for_roles:
            RUNTIME.home_by_role[role] = descriptor.state

        target_router = root_router
        if role_resolver and allowed_roles and SceneRole.ANY.value not in allowed_roles:
            router_key = tuple(sorted(allowed_roles))

            if router_key not in grouped_routers:
                scoped_router = Router(name=f"scenes:{'-'.join(router_key)}")
                _apply_filters(scoped_router, RoleAllowed(role_resolver, allowed_roles))
                grouped_routers[router_key] = scoped_router
                root_router.include_router(scoped_router)

            target_router = grouped_routers[router_key]

        registry.add(scene_cls, router=target_router)

        for entry in descriptor.entrypoints:
            observer = getattr(target_router, entry.observer)
            observer.register(
                scene_cls.as_handler(**entry.handler_kwargs),
                *entry.filters,
            )

    return SceneBootstrapResult(
        router=root_router,
        registry=registry,
        scenes=scenes,
        descriptors=descriptors,
        scene_map={descriptor.state: descriptor.scene for descriptor in descriptors},
        modules=discovered_modules,
    )
