from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any, cast


def _serialize_model(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if is_dataclass(value):
        return dict(asdict(cast(Any, value)))
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__dict__"):
        return {
            key: value
            for key, value in vars(value).items()
            if not key.startswith("_")
        }
    raise TypeError(f"Unsupported state model value: {type(value)!r}")


def _build_model[ModelT](model_cls: type[ModelT], payload: Mapping[str, Any]) -> ModelT:
    validator = getattr(model_cls, "model_validate", None)
    if callable(validator):
        return cast(ModelT, validator(dict(payload)))
    return model_cls(**dict(payload))


class BoundStateModel[ModelT]:
    def __init__(
        self,
        scene: Any,
        *,
        model_cls: type[ModelT],
        key: str,
        default_factory: Any = None,
    ) -> None:
        self.scene = scene
        self.model_cls = model_cls
        self.key = key
        self.default_factory = default_factory

    async def raw(self) -> dict[str, Any]:
        payload = await self.scene.data.get(self.key, {})
        if isinstance(payload, Mapping):
            return dict(payload)
        return {}

    async def get(self) -> ModelT:
        payload = await self.raw()
        if not payload and self.default_factory is not None:
            return self.default_factory()
        return _build_model(self.model_cls, payload)

    async def require(self) -> ModelT:
        payload = await self.raw()
        if not payload and self.default_factory is None:
            raise KeyError(f"Missing state model payload for {self.key!r}")
        return await self.get()

    async def set(self, value: ModelT | Mapping[str, Any] | None = None, **kwargs: Any) -> ModelT:
        payload = _serialize_model(value)
        payload.update(kwargs)
        await self.scene.data.update({self.key: payload})
        return await self.get()

    async def patch(self, **kwargs: Any) -> ModelT:
        payload = await self.raw()
        payload.update(kwargs)
        await self.scene.data.update({self.key: payload})
        return await self.get()

    async def reset(self) -> ModelT:
        if self.default_factory is None:
            await self.scene.data.update({self.key: {}})
            return await self.get()
        value = self.default_factory()
        await self.scene.data.update({self.key: _serialize_model(value)})
        return value

    async def delete(self, *keys: str) -> ModelT:
        payload = await self.raw()
        for key in keys:
            payload.pop(key, None)
        await self.scene.data.update({self.key: payload})
        return await self.get()

    async def pop(self, key: str, default: Any | None = None) -> Any:
        payload = await self.raw()
        value = payload.pop(key, default)
        await self.scene.data.update({self.key: payload})
        return value


class StateModelDescriptor[ModelT]:
    def __init__(
        self,
        model_cls: type[ModelT],
        *,
        key: str,
        default_factory: Any = None,
    ) -> None:
        self.model_cls = model_cls
        self.key = key
        self.default_factory = default_factory

    def __get__(self, instance: Any, owner: type | None = None) -> BoundStateModel[ModelT] | None:
        if instance is None:
            return None
        cache_owner = getattr(instance, "__dict__", None)
        if cache_owner is None:
            return BoundStateModel(
                instance,
                model_cls=self.model_cls,
                key=self.key,
                default_factory=self.default_factory,
            )
        cache = cache_owner.setdefault("_state_model_cache", {})
        accessor = cache.get(self.key)
        if accessor is None:
            accessor = BoundStateModel(
                instance,
                model_cls=self.model_cls,
                key=self.key,
                default_factory=self.default_factory,
            )
            cache[self.key] = accessor
        return accessor


def state_model[ModelT](
    model_cls: type[ModelT],
    *,
    key: str,
    default_factory: Any = None,
) -> StateModelDescriptor[ModelT]:
    return StateModelDescriptor(
        model_cls,
        key=key,
        default_factory=default_factory,
    )


__all__ = ["BoundStateModel", "StateModelDescriptor", "state_model"]
