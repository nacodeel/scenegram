from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ._utils import call_with_optional_args
from .contracts import ProviderValue, SceneModule, SupportsResolve

UNSET = object()


class MissingServiceError(KeyError):
    pass


@dataclass(slots=True)
class MappingContainer:
    values: Mapping[str, ProviderValue]

    def resolve(
        self,
        key: str,
        *,
        scene: Any | None = None,
        module: SceneModule | None = None,
        default: Any = UNSET,
    ) -> Any:
        if key not in self.values:
            if default is not UNSET:
                return default
            raise MissingServiceError(key)
        return self.values[key]


@dataclass(slots=True)
class CompositeContainer:
    containers: Sequence[SupportsResolve]

    def resolve(
        self,
        key: str,
        *,
        scene: Any | None = None,
        module: SceneModule | None = None,
        default: Any = UNSET,
    ) -> Any:
        for container in self.containers:
            value = container.resolve(key, scene=scene, module=module, default=UNSET)
            if value is not UNSET:
                return value
        if default is not UNSET:
            return default
        raise MissingServiceError(key)


@dataclass(slots=True)
class NullContainer:
    def resolve(
        self,
        key: str,
        *,
        scene: Any | None = None,
        module: SceneModule | None = None,
        default: Any = UNSET,
    ) -> Any:
        if default is not UNSET:
            return default
        raise MissingServiceError(key)


def adapt_container(value: SupportsResolve | Mapping[str, ProviderValue] | None) -> SupportsResolve:
    if value is None:
        return NullContainer()
    if hasattr(value, "resolve"):
        return value
    return MappingContainer(value)


def is_provider_callable(value: ProviderValue) -> bool:
    if not callable(value):
        return False

    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError):
        return False

    allowed_names = {"scene", "module"}
    positional_params = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]

    if not positional_params:
        return True
    if len(positional_params) > 2:
        return False
    return all(parameter.name in allowed_names for parameter in positional_params)


async def resolve_service_value(
    value: ProviderValue,
    *,
    scene: Any | None = None,
    module: SceneModule | None = None,
) -> Any:
    if is_provider_callable(value):
        return await call_with_optional_args(value, scene, module)
    return value
