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


def _prepare_call(
    callback: Any,
    *args: Any,
    **kwargs: Any,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        arity = positional_arity(callback)
        call_args = list(args if arity is None else args[:arity])
        return tuple(call_args), {}

    parameters = list(signature.parameters.values())
    remaining_args = list(args)
    call_args: list[Any] = []
    call_kwargs: dict[str, Any] = {}
    consumed_keyword_names: set[str] = set()
    accepts_var_keyword = False

    for parameter in parameters:
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            call_args.extend(remaining_args)
            remaining_args.clear()
            continue

        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            accepts_var_keyword = True
            continue

        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            if remaining_args:
                call_args.append(remaining_args.pop(0))
            continue

        if parameter.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            if parameter.name in kwargs:
                call_kwargs[parameter.name] = kwargs[parameter.name]
                consumed_keyword_names.add(parameter.name)
                continue
            if remaining_args:
                call_args.append(remaining_args.pop(0))
            continue

        if parameter.kind == inspect.Parameter.KEYWORD_ONLY and parameter.name in kwargs:
            call_kwargs[parameter.name] = kwargs[parameter.name]
            consumed_keyword_names.add(parameter.name)

    if accepts_var_keyword:
        for name, value in kwargs.items():
            if name in consumed_keyword_names or name in call_kwargs:
                continue
            call_kwargs[name] = value

    return tuple(call_args), call_kwargs


async def call_with_optional_args(callback: Any, *args: Any, **kwargs: Any) -> Any:
    call_args, call_kwargs = _prepare_call(callback, *args, **kwargs)
    return await maybe_await(callback(*call_args, **call_kwargs))
