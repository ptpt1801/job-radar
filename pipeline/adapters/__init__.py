from .base import REGISTRY, Adapter  # noqa: F401
from . import workday, smartrecruiters, greenhouse, lever, ashby, ybox, vn_boards  # noqa: F401
from .custom import jibe, avature, successfactors  # noqa: F401


def adapter_for(company: dict) -> str:
    """Return registry key for a company config."""
    ats = company.get("ats")
    if ats == "custom":
        return company.get("adapter") or "custom"
    return ats
