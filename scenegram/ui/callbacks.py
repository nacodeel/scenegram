from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, unquote

from aiogram.filters.callback_data import CallbackData

SUPPORTED_NAV_PARAM_TYPES = (str, int, float, bool, type(None))


def _is_supported_nav_value(value: Any) -> bool:
    if isinstance(value, SUPPORTED_NAV_PARAM_TYPES):
        return True
    if isinstance(value, list):
        return all(_is_supported_nav_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_supported_nav_value(item)
            for key, item in value.items()
        )
    return False


def encode_nav_params(params: Mapping[str, Any] | None = None) -> str:
    payload = dict(params or {})
    if not payload:
        return ""
    unsupported = sorted(
        key for key, value in payload.items() if not _is_supported_nav_value(value)
    )
    if unsupported:
        joined = ", ".join(unsupported)
        raise TypeError(
            "Navigate params support only JSON-serializable scalars, lists, and dicts. "
            f"Unsupported keys: {joined}"
        )

    chunks: list[str] = []
    for key, value in payload.items():
        encoded_key = quote(key, safe="-_.~")
        if value is None:
            encoded_value = "n"
        elif isinstance(value, bool):
            encoded_value = f"b{int(value)}"
        elif isinstance(value, int) and not isinstance(value, bool):
            encoded_value = f"i{value}"
        elif isinstance(value, float):
            encoded_value = f"f{value!r}"
        elif isinstance(value, str):
            encoded_value = f"s{quote(value, safe='-_.~')}"
        else:
            raw = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            raw = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
            encoded_value = f"j{raw}"
        chunks.append(f"{encoded_key}={encoded_value}")
    return "&".join(chunks)


def decode_nav_params(payload: str) -> dict[str, Any]:
    if not payload:
        return {}
    decoded: dict[str, Any] = {}
    for chunk in payload.split("&"):
        if "=" not in chunk:
            raise ValueError(f"Malformed navigation params segment: {chunk!r}")
        raw_key, raw_value = chunk.split("=", 1)
        key = unquote(raw_key)
        value_type = raw_value[:1]
        value_payload = raw_value[1:]
        if value_type == "n":
            value = None
        elif value_type == "b":
            value = value_payload == "1"
        elif value_type == "i":
            value = int(value_payload)
        elif value_type == "f":
            value = float(value_payload)
        elif value_type == "s":
            value = unquote(value_payload)
        elif value_type == "j":
            padding = "=" * (-len(value_payload) % 4)
            raw = base64.urlsafe_b64decode(f"{value_payload}{padding}".encode("ascii"))
            value = json.loads(raw.decode("utf-8"))
        else:
            raise ValueError(f"Unsupported navigation param type prefix: {value_type!r}")
        decoded[key] = value
    return decoded


class Navigate(CallbackData, prefix="nav"):
    action: str
    target: str
    params: str = ""

    @classmethod
    def open(cls, target: str, **params: Any) -> Navigate:
        return cls(action="open", target=target, params=encode_nav_params(params))

    @classmethod
    def back(cls, target: str = "", **params: Any) -> Navigate:
        return cls(action="back", target=target, params=encode_nav_params(params))

    @classmethod
    def home(cls, target: str = "", **params: Any) -> Navigate:
        return cls(action="home", target=target, params=encode_nav_params(params))

    @classmethod
    def replace(cls, target: str, **params: Any) -> Navigate:
        return cls(action="replace", target=target, params=encode_nav_params(params))

    @classmethod
    def cancel(cls, target: str = "", **params: Any) -> Navigate:
        return cls(action="cancel", target=target, params=encode_nav_params(params))

    @property
    def params_payload(self) -> dict[str, Any]:
        return decode_nav_params(self.params)

    def pack(self) -> str:
        if not self.params:
            return f"{self.__prefix__}:{self.action}:{self.target}"
        return super().pack()

    @classmethod
    def unpack(cls, value: str) -> Navigate:
        prefix, *parts = value.split(cls.__separator__)
        names = cls.model_fields.keys()

        if prefix != cls.__prefix__:
            raise ValueError(f"Bad prefix ({prefix!r} != {cls.__prefix__!r})")

        if len(parts) == 2:
            payload = dict(zip(names, [*parts, ""], strict=True))
            return cls(**payload)

        return super().unpack(value)


class PageNav(CallbackData, prefix="page"):
    page: int
