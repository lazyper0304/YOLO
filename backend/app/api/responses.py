"""Unified API response helper functions."""
from typing import Any


def success_response(data: Any = None, message: str = "ok") -> dict:
    """Build a standard success response."""
    return {"code": 0, "message": message, "data": data}


def paginated_response(
    items: list[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Build a standard paginated response."""
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


def error_response(code: int, message: str, data: Any = None) -> dict:
    """Build a standard error response."""
    return {"code": code, "message": message, "data": data}
