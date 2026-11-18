"""VietnamWorks / TopCV. Lowest priority, DISABLED by default.

Only to be enabled after reading each site's robots.txt and terms of use and getting the
repo owner's approval (BUILD_PROMPT 5.1). Not implemented on purpose.
"""
from __future__ import annotations

from .base import Adapter, register


@register("vietnamworks")
@register("topcv")
class VNBoardsAdapter(Adapter):
    source = "vietnamworks"

    def fetch(self, company, known_ids=None, reuse=None):
        return []
