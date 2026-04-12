from __future__ import annotations

import inspect
from typing import Any


def positional_arity(callback: Any) -> int | None:
    signature = inspect.signature(callback)
    parameters = list(signature.parameters.values())

    if any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters):
        return None

    return len(
        [
            parameter
            for parameter in parameters
            if parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
    )


async def maybe_await(result: Any) -> Any:
    if inspect.isawaitable(result):
        return await result
    return result


async def call_with_optional_args(callback: Any, *args: Any) -> Any:
    arity = positional_arity(callback)
    call_args = args if arity is None else args[:arity]
    return await maybe_await(callback(*call_args))
