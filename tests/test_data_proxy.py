from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from scenegram import SceneDataProxy


@dataclass(slots=True)
class DraftData:
    name: str | None = None
    step: str = "draft"


class UserModel(BaseModel):
    name: str
    age: int


@pytest.mark.asyncio
async def test_pick_returns_values_in_requested_order(wizard) -> None:
    wizard.data = {"name": "Alice", "age": 30}
    proxy = SceneDataProxy(wizard)

    assert await proxy.pick("age", "name") == (30, "Alice")


@pytest.mark.asyncio
async def test_require_returns_value(wizard) -> None:
    wizard.data = {"name": "Alice"}
    proxy = SceneDataProxy(wizard)

    assert await proxy.require("name") == "Alice"


@pytest.mark.asyncio
async def test_require_raises_on_missing_key(wizard) -> None:
    proxy = SceneDataProxy(wizard)

    with pytest.raises(KeyError):
        await proxy.require("name")


@pytest.mark.asyncio
async def test_require_many_collects_all_required_values(wizard) -> None:
    wizard.data = {"name": "Alice", "age": 30}
    proxy = SceneDataProxy(wizard)

    assert await proxy.require_many("name", "age") == ("Alice", 30)


@pytest.mark.asyncio
async def test_update_accepts_mapping_and_kwargs(wizard) -> None:
    proxy = SceneDataProxy(wizard)

    result = await proxy.update({"name": "Alice"}, age=30)

    assert result == {"name": "Alice", "age": 30}


@pytest.mark.asyncio
async def test_set_replaces_state_payload(wizard) -> None:
    wizard.data = {"obsolete": True}
    proxy = SceneDataProxy(wizard)

    await proxy.set({"name": "Alice"}, age=30)

    assert wizard.data == {"name": "Alice", "age": 30}


@pytest.mark.asyncio
async def test_pop_returns_single_value(wizard) -> None:
    wizard.data = {"name": "Alice", "age": 30}
    proxy = SceneDataProxy(wizard)

    value = await proxy.pop("name")

    assert value == "Alice"
    assert wizard.data == {"age": 30}


@pytest.mark.asyncio
async def test_pop_returns_multiple_values(wizard) -> None:
    wizard.data = {"name": "Alice", "age": 30, "city": "Moscow"}
    proxy = SceneDataProxy(wizard)

    value = await proxy.pop("name", "city")

    assert value == ("Alice", "Moscow")
    assert wizard.data == {"age": 30}


@pytest.mark.asyncio
async def test_discard_removes_keys_if_present(wizard) -> None:
    wizard.data = {"name": "Alice", "age": 30, "city": "Moscow"}
    proxy = SceneDataProxy(wizard)

    await proxy.discard("age", "missing")

    assert wizard.data == {"name": "Alice", "city": "Moscow"}


@pytest.mark.asyncio
async def test_model_builds_dataclass(wizard) -> None:
    wizard.data = {"name": "Alice", "step": "confirm", "ignored": True}
    proxy = SceneDataProxy(wizard)

    model = await proxy.model(DraftData)

    assert model == DraftData(name="Alice", step="confirm")


@pytest.mark.asyncio
async def test_model_builds_pydantic_model(wizard) -> None:
    wizard.data = {"name": "Alice", "age": 30}
    proxy = SceneDataProxy(wizard)

    model = await proxy.model(UserModel)

    assert model == UserModel(name="Alice", age=30)


@pytest.mark.asyncio
async def test_clear_resets_scene_data(wizard) -> None:
    wizard.data = {"name": "Alice"}
    proxy = SceneDataProxy(wizard)

    await proxy.clear()

    assert wizard.data == {}
