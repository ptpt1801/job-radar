"""Adapter interface. Each adapter turns one company config into a list of RawJob dicts.

RawJob keys (all optional except source, source_job_id, title, url):
  source, source_job_id, title, url, company_name_raw,
  location_raw, country_code, city_raw, address_raw,
  description (plain text), posted_at (ISO), posted_text, deadline (YYYY-MM-DD),
  employment_type_raw, level_raw, function_raw, work_mode,
  salary (dict per schema or None), is_open (bool or None), lang_hint
"""
from __future__ import annotations

from typing import Callable

from ..http import PoliteClient, client

from ..text import VN_WORDS, looks_vn  # noqa: F401  (re-export)


class Adapter:
    source = "custom"

    def __init__(self, http: PoliteClient | None = None):
        self.http = http or client()

    def fetch(self, company: dict, known_ids: set[str] | None = None,
              reuse: Callable[[str], dict | None] | None = None) -> list[dict]:
        """known_ids: source_job_ids already stored (adapters may skip detail calls for these).
        reuse(source_job_id) -> previous RawJob-ish dict, or None."""
        raise NotImplementedError


REGISTRY: dict[str, type[Adapter]] = {}


def register(name: str):
    def deco(cls):
        REGISTRY[name] = cls
        return cls
    return deco
