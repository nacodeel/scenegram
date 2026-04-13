from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from aiogram import Router
from aiogram.filters import Command, Filter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.scene import SceneRegistry

from .contracts import SceneCleanup, SceneMiddleware, SceneModule, scene_middleware
from .di import adapt_container
from .roles import SceneRole, normalize_role, normalize_roles
from .runtime import DEFAULT_CLEANUP, RUNTIME, RoleResolver
from .security import SecureScenesManagerProxy


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


class SecureScenesMiddleware:
    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        manager = data.get("scenes")
        if manager is not None and not isinstance(manager, SecureScenesManagerProxy):
            data["scenes"] = SecureScenesManagerProxy(manager)
        return await handler(event, data)


class SceneErrorMiddleware:
    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            await RUNTIME.emit(
                "scene.unhandled_error",
                event=event,
                error=repr(exc),
            )
            raise


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


def _resolve_middleware_instance(
    binding: SceneMiddleware,
    *,
    scene_cls: type | None = None,
    module: SceneModule | None = None,
) -> Any:
    middleware = binding.middleware
    if not binding.factory:
        return middleware
    if inspect.isclass(middleware):
        return middleware()

    try:
        signature = inspect.signature(middleware)
    except (TypeError, ValueError):
        return middleware()

    kwargs: dict[str, Any] = {}
    if "scene" in signature.parameters:
        kwargs["scene"] = scene_cls
    if "module" in signature.parameters:
        kwargs["module"] = module
    return middleware(**kwargs)


def _apply_middlewares(
    router: Router,
    middlewares: Sequence[SceneMiddleware],
    *,
    scene_cls: type | None = None,
    module: SceneModule | None = None,
) -> None:
    for binding in middlewares:
        instance = _resolve_middleware_instance(
            binding,
            scene_cls=scene_cls,
            module=module,
        )
        for observer_name in binding.observers:
            observer = getattr(router, observer_name, None)
            if observer is None:
                raise ValueError(f"Router has no observer named {observer_name!r}")
            manager = observer.outer_middleware if binding.outer else observer.middleware
            manager(instance)


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


def discover_callback_prefixes(
    package_name: str | Sequence[str],
    *,
    extra_modules: Sequence[str] | None = None,
) -> dict[str, str]:
    discovered: dict[str, str] = {}

    module_names: list[str] = []
    for root_package in _normalize_packages(package_name):
        module_names.extend(_discover_modules(root_package))
    module_names.extend(extra_modules or ())

    for module_name in module_names:
        module = importlib.import_module(module_name)
        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate is CallbackData:
                continue
            if not issubclass(candidate, CallbackData):
                continue
            if candidate.__module__ != module.__name__:
                continue
            prefix = getattr(candidate, "__prefix__", None)
            if not isinstance(prefix, str) or not prefix:
                continue
            owner = f"{candidate.__module__}.{candidate.__name__}"
            existing = discovered.get(prefix)
            if existing is not None and existing != owner:
                raise RuntimeError(
                    f"Callback prefix collision for '{prefix}': {existing} vs {owner}"
                )
            discovered[prefix] = owner

    return discovered


def _reserved_callback_prefixes() -> dict[str, str]:
    from .packs import CrudAction
    from .patterns import ConfirmAction, FormAction, StepAction
    from .ui.callbacks import Navigate, PageNav

    callback_types = (Navigate, PageNav, ConfirmAction, StepAction, FormAction, CrudAction)
    return {
        callback_type.__prefix__: f"{callback_type.__module__}.{callback_type.__name__}"
        for callback_type in callback_types
    }


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
    middlewares: Sequence[SceneMiddleware] | None = None,
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
    RUNTIME.register_descriptors(descriptors)
    RUNTIME.register_callback_prefixes(
        {
            **_reserved_callback_prefixes(),
            **discover_callback_prefixes(package_name),
        }
    )

    grouped_routers: dict[tuple[str, ...], Router] = {}
    global_middlewares = tuple(middlewares or ())

    for descriptor in descriptors:
        scene_cls = descriptor.scene
        allowed_roles = descriptor.roles
        module = discovered_modules.get(descriptor.scene_module or "")

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

        scene_router = Router(name=f"scene:{descriptor.state}")
        registry.add(scene_cls)

        _apply_middlewares(
            scene_router,
            (
                scene_middleware(SecureScenesMiddleware(), "message", "callback_query"),
                scene_middleware(SceneErrorMiddleware(), "message", "callback_query"),
                *global_middlewares,
                *(module.middlewares if module is not None else ()),
                *tuple(getattr(scene_cls, "middlewares", ())),
            ),
            scene_cls=scene_cls,
            module=module,
        )
        scene_router.include_router(scene_cls.as_router())

        for entry in descriptor.entrypoints:
            observer = getattr(scene_router, entry.observer)
            observer.register(
                scene_cls.as_handler(**entry.handler_kwargs),
                *entry.filters,
            )

        target_router.include_router(scene_router)

    return SceneBootstrapResult(
        router=root_router,
        registry=registry,
        scenes=scenes,
        descriptors=descriptors,
        scene_map={descriptor.state: descriptor.scene for descriptor in descriptors},
        modules=discovered_modules,
    )
