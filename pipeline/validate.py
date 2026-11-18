"""JSON-schema validation for published jobs."""
from __future__ import annotations

import functools
import json

from jsonschema import Draft202012Validator, FormatChecker

from .config import ROOT


@functools.lru_cache
def _schema():
    return json.loads((ROOT / "schemas" / "job.schema.json").read_text(encoding="utf-8"))


@functools.lru_cache
def allowed_keys() -> frozenset:
    return frozenset(_schema()["properties"].keys())


@functools.lru_cache
def validator():
    return Draft202012Validator(_schema(), format_checker=FormatChecker())


def errors(job: dict) -> list[str]:
    return [f"{'/'.join(map(str, e.path))}: {e.message}" for e in validator().iter_errors(job)]
