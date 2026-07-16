#!/usr/bin/env python3
"""Merge per-run STAC outputs into one multi-temporal collection.

Each run directory produced by ``csdr-cog-cruncher`` is a self-contained STAC
catalog holding a single collection and a single item (one time slice). This
tool re-parents every item under one shared collection so the products read as
one multi-temporal dataset rather than as separate single-timestamp catalogs.

The idiomatic STAC model for multi-temporal data is *one item per epoch inside
one collection* -- not one item carrying every epoch as separate assets. Each
item keeps one representative datetime and its COG asset; the collection
preserves every true epoch interval so clients can filter and stack by time.

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pystac

from csdr_cog_cruncher.config import load_config

# Where the COGs are published, shared with the per-run catalog writer so both address assets
# identically.
from csdr_cog_cruncher.publish import (
    DEFAULT_HTTPS_BASE,
    DEFAULT_S3_BASE,
    set_published_asset,
)

SCIENTIFIC_EXT = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"

# Collection-level fields carried verbatim from the source collections.
_CARRIED_COLLECTION_FIELDS = ("providers", "keywords", "sci:doi", "sci:citation")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


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


def _run_epoch(
    run_dir: Path, item: pystac.Item, collection_dict: dict[str, Any]
) -> tuple[datetime, datetime]:
    """The (start, end) span this run covers.

    Read from the run's collection temporal extent, which is authoritative and present whether
    or not the item still carries a start/end range of its own (older runs do, newer ones do
    not - see _publish_single_datetime).
    """
    interval = collection_dict.get("extent", {}).get("temporal", {}).get("interval") or []
    if interval and interval[0] and all(interval[0][:2]):
        return _parse_timestamp(interval[0][0]), _parse_timestamp(interval[0][1])
    # Fall back to the item's own range for hand-built runs with no collection extent.
    start = item.properties.get("start_datetime")
    end = item.properties.get("end_datetime")
    if start and end:
        return _parse_timestamp(start), _parse_timestamp(end)
    raise SystemExit(
        f"{run_dir}: cannot determine the epoch - no collection temporal extent and no "
        "start_datetime/end_datetime on the item."
    )


def _publish_single_datetime(item: pystac.Item, epoch: tuple[datetime, datetime]) -> None:
    """Publish the item with one representative `datetime` and no start/end range.

    rustac (which backs the csdr STAC-Geoparquet index) ignores `datetime` whenever an item also
    carries a start/end range, and then only matches a query interval that *contains* the item's
    whole range - so an ordinary `datetime=2020` search matches nothing and every downstream area
    comes back as 0. The span is not lost: this collection's temporal extent declares the overall
    interval and each epoch.
    """
    start, end = epoch
    if item.datetime is None:
        item.datetime = start + (end - start) / 2
    item.properties.pop("start_datetime", None)
    item.properties.pop("end_datetime", None)


def _rewrite_asset(
    item: pystac.Item, run_name: str, https_base: str, s3_base: str | None
) -> None:
    """Point the data asset at its published location and add an s3 alternate.

    Per-run catalogs already publish this way, so for them this is a no-op; it still matters for
    older runs whose assets were written as local paths, and when a non-default base is passed.
    """

    set_published_asset(item, run_name, https_base=https_base, s3_base=s3_base)


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
    item_epochs: dict[str, tuple[datetime, datetime]] = {}
    source_collection: dict[str, Any] | None = None
    source_titles: list[str | None] = []
    seen_item_ids: set[str] = set()
    for run_dir in run_dirs:
        item, collection_dict = _load_run(run_dir)
        source_titles.append(collection_dict.get("title"))
        if source_collection is None:
            source_collection = collection_dict
        elif collection_dict["id"] != source_collection["id"]:
            raise SystemExit(
                f"{run_dir}: collection {collection_dict['id']!r} does not match "
                f"{source_collection['id']!r}"
            )
        if item.id in seen_item_ids:
            raise SystemExit(f"{run_dir}: duplicate STAC item id {item.id!r}")
        seen_item_ids.add(item.id)
        _rewrite_asset(item, run_dir.name, https_base, s3_base)
        _reset_structural_links(item)
        item_epochs[item.id] = _run_epoch(run_dir, item, collection_dict)
        _publish_single_datetime(item, item_epochs[item.id])
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
    # This collection is now the only place the per-epoch spans are declared, since the items
    # publish a single representative datetime instead - see _publish_single_datetime.
    epochs = [item_epochs[item.id] for item in items]
    epochs.sort(key=lambda pair: pair[0])
    overall = [min(s for s, _ in epochs), max(e for _, e in epochs)]
    intervals = [overall] + [list(pair) for pair in epochs]

    # Product configs may provide a stable collection title distinct from each epoch's item
    # title. This avoids trying to infer product identity by parsing year-like title suffixes.
    base_title = (
        source_titles[0]
        if source_titles[0] and len(set(source_titles)) == 1
        else collection_id
    )
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
        "--config",
        type=Path,
        help="Product config supplying href_base and s3_base defaults",
    )
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
        default=None,
        help="Override the config's primary asset URL base",
    )
    parser.add_argument(
        "--s3-base",
        default=None,
        help="Override the config's s3:// alternate base; empty string to disable",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the catalog against remote STAC schemas (needs network)",
    )
    args = parser.parse_args()

    config = load_config(args.config) if args.config else None
    https_base = args.href_base or (config.href_base if config else DEFAULT_HTTPS_BASE)
    if args.s3_base is not None:
        s3_base = args.s3_base or None
    else:
        s3_base = config.s3_base if config else DEFAULT_S3_BASE

    merge(
        args.runs,
        args.out,
        collection_id=args.collection_id,
        title=args.title,
        description=args.description,
        https_base=https_base,
        s3_base=s3_base,
        validate=args.validate,
    )


if __name__ == "__main__":
    main()
