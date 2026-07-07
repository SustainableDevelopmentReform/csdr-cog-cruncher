#!/usr/bin/env python3
"""Merge per-run STAC outputs into one multi-temporal collection.

Each run directory produced by ``csdr-cog-cruncher`` is a self-contained STAC
catalog holding a single collection and a single item (one time slice). This
tool re-parents every item under one shared collection so the products read as
one multi-temporal dataset rather than as separate single-timestamp catalogs.

The idiomatic STAC model for multi-temporal data is *one item per epoch inside
one collection* -- not one item carrying every epoch as separate assets. Each
item keeps its own datetime interval and COG asset; the collection spans them
all so clients can filter/stack by time.

Asset hrefs are rewritten to where the COGs actually live (public S3 by
default). The HTTPS URL is the primary href (readable by browsers, STAC
Browser, TiTiler, and AWS tools via GDAL /vsicurl/); the matching ``s3://`` URI
is attached as an ``alternate`` href for S3-native workflows.

Example
-------
    .venv/bin/python scripts/merge_stac.py \
        outputs/seagrass_2019_2020 \
        outputs/seagrass_2023_2024 \
        --out outputs/seagrass_multitemporal
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pystac

# Public locations for the merged COGs. Each run's data asset resolves to
# ``{base}/{run_dir_name}/{filename}`` -- matching the bucket layout the
# outputs were synced into.
DEFAULT_HTTPS_BASE = (
    "https://csdr-public-datasets.s3.ap-southeast-2.amazonaws.com/cog-cruncher-outputs"
)
DEFAULT_S3_BASE = "s3://csdr-public-datasets/cog-cruncher-outputs"

ALTERNATE_ASSETS_EXT = (
    "https://stac-extensions.github.io/alternate-assets/v1.2.0/schema.json"
)
SCIENTIFIC_EXT = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"

# Collection-level fields carried verbatim from the source collections.
_CARRIED_COLLECTION_FIELDS = ("providers", "keywords", "sci:doi", "sci:citation")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _strip_epoch_suffix(title: str) -> str:
    """Drop a trailing ", 2019-2020"-style epoch from a per-run title."""

    return re.sub(r",?\s*\d{4}\s*[-–]\s*\d{4}\s*$", "", title).strip()


def _load_run(run_dir: Path) -> tuple[pystac.Item, dict[str, Any]]:
    """Return the single item and raw collection dict for a run directory."""

    catalog = pystac.Catalog.from_file(str(run_dir / "catalog.json"))
    items = list(catalog.get_items(recursive=True))
    if len(items) != 1:
        raise SystemExit(
            f"{run_dir}: expected exactly one STAC item, found {len(items)}"
        )
    collections = list(catalog.get_collections())
    if not collections:
        raise SystemExit(f"{run_dir}: no STAC collection found")
    collection_path = collections[0].get_self_href()
    with open(collection_path, encoding="utf-8") as handle:
        collection_dict = json.load(handle)
    return items[0], collection_dict


def _rewrite_asset(
    item: pystac.Item, run_name: str, https_base: str, s3_base: str | None
) -> None:
    """Point the data asset at its published location and add an s3 alternate."""

    asset = item.assets["data"]
    filename = asset.href.rstrip("/").rsplit("/", 1)[-1]
    asset.href = f"{https_base.rstrip('/')}/{run_name}/{filename}"
    if s3_base:
        asset.extra_fields["alternate"] = {
            "s3": {
                "href": f"{s3_base.rstrip('/')}/{run_name}/{filename}",
                "title": "S3 access",
            }
        }
        if ALTERNATE_ASSETS_EXT not in item.stac_extensions:
            item.stac_extensions.append(ALTERNATE_ASSETS_EXT)


def _reset_structural_links(item: pystac.Item) -> None:
    """Drop links to the item's old catalog so pystac rebuilds them cleanly."""

    for rel in ("root", "parent", "collection", "self"):
        item.remove_links(rel)


def merge(
    run_dirs: list[Path],
    out_dir: Path,
    *,
    collection_id: str | None,
    title: str | None,
    description: str | None,
    https_base: str,
    s3_base: str | None,
    validate: bool,
) -> None:
    items: list[pystac.Item] = []
    source_collection: dict[str, Any] | None = None
    for run_dir in run_dirs:
        item, collection_dict = _load_run(run_dir)
        if source_collection is None:
            source_collection = collection_dict
        _rewrite_asset(item, run_dir.name, https_base, s3_base)
        _reset_structural_links(item)
        items.append(item)

    assert source_collection is not None
    collection_id = collection_id or source_collection["id"]
    license_id = source_collection.get("license", items[0].properties.get("license"))

    # Spatial extent: overall union bbox first, then each item's own bbox.
    item_bboxes = [list(item.bbox) for item in items]
    union_bbox = [
        min(b[0] for b in item_bboxes),
        min(b[1] for b in item_bboxes),
        max(b[2] for b in item_bboxes),
        max(b[3] for b in item_bboxes),
    ]

    # Temporal extent: overall interval first, then each epoch (STAC spec).
    epochs = [
        (
            _parse_timestamp(item.properties["start_datetime"]),
            _parse_timestamp(item.properties["end_datetime"]),
        )
        for item in items
    ]
    epochs.sort(key=lambda pair: pair[0])
    overall = [min(s for s, _ in epochs), max(e for _, e in epochs)]
    intervals = [overall] + [list(pair) for pair in epochs]

    base_title = _strip_epoch_suffix(items[0].properties.get("title", collection_id))
    if title is None:
        title = f"{base_title} (multi-temporal, {overall[0].year}–{overall[1].year})"
    if description is None:
        epoch_labels = ", ".join(f"{s.year}–{e.year}" for s, e in epochs)
        lead = base_title[:1].lower() + base_title[1:] if base_title else "dataset"
        description = (
            f"Multi-temporal {lead} combining {len(items)} time slices "
            f"({epoch_labels}). Each STAC Item is a single-epoch Cloud Optimized "
            "GeoTIFF; the collection groups them as one time series."
        )

    extent = pystac.Extent(
        spatial=pystac.SpatialExtent([union_bbox] + item_bboxes),
        temporal=pystac.TemporalExtent(intervals),
    )
    collection = pystac.Collection(
        id=collection_id,
        description=description,
        extent=extent,
        title=title,
        license=license_id,
    )
    for field in _CARRIED_COLLECTION_FIELDS:
        if field in source_collection:
            collection.extra_fields[field] = source_collection[field]
    if any(f in source_collection for f in ("sci:doi", "sci:citation")):
        collection.stac_extensions = [SCIENTIFIC_EXT]

    for item in items:
        collection.add_item(item)

    catalog = pystac.Catalog(
        id=f"{collection_id}-catalog",
        description=f"Static STAC catalog for the multi-temporal {base_title} dataset.",
        title=title,
    )
    catalog.add_child(collection)

    catalog.normalize_hrefs(str(out_dir))
    if validate:
        catalog.validate_all()
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)

    print(f"Wrote merged catalog to {out_dir}")
    print(f"  collection: {collection_id}  ({len(items)} items)")
    for item in items:
        print(f"    - {item.id}: {item.assets['data'].href}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path, help="Run output directories to merge")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/seagrass_multitemporal"),
        help="Directory for the merged catalog (default: outputs/seagrass_multitemporal)",
    )
    parser.add_argument("--collection-id", default=None, help="Override merged collection id")
    parser.add_argument("--title", default=None, help="Override collection title")
    parser.add_argument("--description", default=None, help="Override collection description")
    parser.add_argument(
        "--href-base",
        default=DEFAULT_HTTPS_BASE,
        help="Base URL for primary asset hrefs (default: public S3 HTTPS)",
    )
    parser.add_argument(
        "--s3-base",
        default=DEFAULT_S3_BASE,
        help="Base s3:// URI for alternate asset hrefs; empty string to disable",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the catalog against remote STAC schemas (needs network)",
    )
    args = parser.parse_args()

    merge(
        args.runs,
        args.out,
        collection_id=args.collection_id,
        title=args.title,
        description=args.description,
        https_base=args.href_base,
        s3_base=args.s3_base or None,
        validate=args.validate,
    )


if __name__ == "__main__":
    main()
