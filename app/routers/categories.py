from fastapi import APIRouter
from ..models import JobCategory

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("/")
async def list_categories():
    return [
        {"id": c.value, "label": JobCategory.icelandic_label(c.value), "icon": _icon(c.value)}
        for c in JobCategory
    ]


def _icon(cat: str) -> str:
    icons = {
        "rafvirkjun": "fa-bolt",
        "pipulagnir": "fa-wrench",
        "byggingarvinna": "fa-hard-hat",
        "malun": "fa-paint-roller",
        "gardyrkja": "fa-seedling",
        "hreinsun": "fa-broom",
        "husgagnasmidi": "fa-chair",
        "smidi": "fa-hammer",
        "lagningar": "fa-tools",
        "lagnir": "fa-water",
        "rafeindaverk": "fa-microchip",
        "hjolun": "fa-weight-hanging",
        "annad": "fa-ellipsis-h",
    }
    return icons.get(cat, "fa-circle")
