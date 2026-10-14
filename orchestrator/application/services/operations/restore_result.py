"""Rebuild domain result values from safe durable receipt representations."""

from __future__ import annotations

import types
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Union, get_args, get_origin, get_type_hints


def restore_result(value: object, target: object) -> object:
    origin = get_origin(target)
    if origin in (types.UnionType, Union):
        for choice in get_args(target):
            if choice is type(None) and value is None:
                return None
            if is_dataclass(choice) and isinstance(value, dict):
                return restore_result(value, choice)
        return value
    if origin in (tuple, list) and isinstance(value, (list, tuple)):
        args = get_args(target)
        values = [restore_result(item, args[0] if args else object) for item in value]
        return tuple(values) if origin is tuple else values
    if origin is dict and isinstance(value, dict):
        args = get_args(target)
        return {restore_result(key, args[0]): restore_result(item, args[1]) for key, item in value.items()} if len(args) == 2 else dict(value)
    if isinstance(target, type) and issubclass(target, Enum):
        return target(value)
    if isinstance(target, type) and is_dataclass(target) and isinstance(value, dict):
        hints = get_type_hints(target)
        return target(
            **{
                field.name: restore_result(
                    value[field.name], hints.get(field.name, object)
                )
                for field in fields(target)
                if field.name in value
            }
        )
    return value
