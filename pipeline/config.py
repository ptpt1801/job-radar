"""Config loading helpers."""
from __future__ import annotations

import functools
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
SITE = ROOT / "site"


def _load(name: str):
    with open(CONFIG / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


@functools.lru_cache
def settings() -> dict:
    return _load("settings.yaml")


@functools.lru_cache
def taxonomy() -> dict:
    return _load("taxonomy.yaml")


@functools.lru_cache
def exclusions() -> dict:
    return _load("exclusions.yaml")


@functools.lru_cache
def companies() -> list[dict]:
    return _load("companies.yaml")["companies"]
