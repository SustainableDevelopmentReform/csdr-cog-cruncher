"""Product metadata validation.

Product identity belongs in workflow configuration, not in this generic module.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any


def _parse_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Product metadata {field_name} must be an ISO 8601 string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"Product metadata {field_name} must be a valid ISO 8601 datetime."
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Product metadata {field_name} must include a timezone.")
    return parsed


def validate_product_metadata(metadata: dict[str, Any], band_count: int) -> dict[str, Any]:
    """Validate the metadata fields consumed by the raster and STAC writers."""

    if not isinstance(metadata, dict):
        raise ValueError("product_metadata must be a mapping.")

    required = {
        "title",
        "description",
        "license",
        "start_datetime",
        "end_datetime",
        "gsd",
        "bands",
    }
    missing = sorted(required - metadata.keys())
    if missing:
        raise ValueError(f"Product metadata is missing required fields: {', '.join(missing)}")

    for field_name in ("title", "description", "license"):
        if not isinstance(metadata[field_name], str) or not metadata[field_name].strip():
            raise ValueError(f"Product metadata {field_name} must be a non-empty string.")
    for field_name in ("collection_title", "collection_description"):
        if field_name in metadata and (
            not isinstance(metadata[field_name], str) or not metadata[field_name].strip()
        ):
            raise ValueError(f"Product metadata {field_name} must be a non-empty string.")

    start = _parse_datetime(metadata["start_datetime"], "start_datetime")
    end = _parse_datetime(metadata["end_datetime"], "end_datetime")
    if start >= end:
        raise ValueError("Product metadata start_datetime must be before end_datetime.")
    if metadata.get("datetime") is not None:
        nominal = _parse_datetime(metadata["datetime"], "datetime")
        if not start <= nominal <= end:
            raise ValueError(
                "Product metadata datetime must fall within start_datetime and end_datetime."
            )

    gsd = metadata["gsd"]
    if not isinstance(gsd, (int, float)) or isinstance(gsd, bool) or gsd <= 0:
        raise ValueError("Product metadata gsd must be a positive number.")

    bands = metadata["bands"]
    if not isinstance(bands, list) or len(bands) != band_count:
        raise ValueError(
            f"Product metadata defines {len(bands) if isinstance(bands, list) else 0} "
            f"bands, but the source tiles contain {band_count}."
        )
    for index, band in enumerate(bands, start=1):
        if not isinstance(band, dict) or not band.get("name"):
            raise ValueError(f"Product metadata band {index} must define a name.")

    return deepcopy(metadata)
