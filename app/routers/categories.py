from fastapi import APIRouter
from ..models import JobCategory

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("/")
async def list_categories():
    return [
        {"id": c.value, "label": JobCategory.icelandic_label(c.value)}
        for c in JobCategory
    ]
