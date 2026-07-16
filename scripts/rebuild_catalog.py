#!/usr/bin/env python
"""Rewrite a finished run's STAC catalog without rebuilding its COG.

The mosaic is the expensive part of a run and STAC metadata is the part that changes - a
correction to how items are published should not cost hours of re-mosaicking. This reads the
grid the run already recorded in ``grid.json`` plus the run's config, and re-runs the catalog
writer over the existing ``mosaic.tif``.

Usage
-----
    .venv/bin/python scripts/rebuild_catalog.py \
        --config configs/seagrass-2019-2020.yaml \
        --run outputs/seagrass_2019_2020
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pystac
import rasterio

from csdr_cog_cruncher.config import load_config
from csdr_cog_cruncher.grid import GridSpec
from csdr_cog_cruncher.metadata import validate_product_metadata
from csdr_cog_cruncher.stac import build_catalog


def _load_grid(run_dir: Path) -> GridSpec:
    with open(run_dir / "grid.json", encoding="utf-8") as handle:
        raw = json.load(handle)
    left, bottom, right, top = raw["bounds"]
    return GridSpec(
        crs_wkt=raw["crs_wkt"],
        resolution=tuple(raw["resolution"]),
        left=left,
        bottom=bottom,
        right=right,
        top=top,
        width=raw["width"],
        height=raw["height"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Run config YAML")
    parser.add_argument("--run", required=True, type=Path, help="Run output directory")
    args = parser.parse_args()

    config = load_config(args.config)

    run_dir: Path = args.run
    data_path = run_dir / "mosaic.tif"
    if not data_path.exists():
        raise SystemExit(f"{data_path} not found - nothing to describe.")
    with rasterio.open(data_path) as dataset:
        dtype = dataset.dtypes[0]
        band_count = dataset.count
    product_metadata = validate_product_metadata(config.product_metadata, band_count)

    catalog_path, collection_path, item_path = build_catalog(
        output_dir=run_dir,
        product_id=config.product_id,
        data_path=data_path,
        grid=_load_grid(run_dir),
        collection_id=config.collection_id,
        product_metadata=product_metadata,
        dtype=dtype,
        asset_media_type=pystac.MediaType.COG,
        https_base=config.href_base,
        s3_base=config.s3_base,
    )
    print(f"Rewrote catalog for {run_dir}")
    for path in (catalog_path, collection_path, item_path):
        print(f"  {path}")


if __name__ == "__main__":
    main()
