"""Validation helpers for raster outputs and STAC documents."""

from __future__ import annotations

from pathlib import Path

import pystac
import rasterio
from rasterio.crs import CRS

from csdr_cog_cruncher.grid import GridSpec
from csdr_cog_cruncher.inventory import InventorySummary


def validate_raster(path: Path, grid: GridSpec, summary: InventorySummary, *, require_overviews: bool) -> None:
    with rasterio.open(path) as dataset:
        if dataset.width != grid.width or dataset.height != grid.height:
            raise ValueError("Output raster dimensions do not match the expected grid.")
        if dataset.count != summary.count:
            raise ValueError("Output raster band count does not match the source inventory.")
        if dataset.dtypes[0] != summary.dtype:
            raise ValueError("Output raster dtype does not match the source inventory.")
        if dataset.crs != CRS.from_wkt(summary.crs_wkt):
            raise ValueError("Output raster CRS does not match the source inventory.")
        actual_bounds = tuple(float(value) for value in dataset.bounds)
        expected_bounds = tuple(float(value) for value in grid.bounds)
        if any(abs(actual - expected) > 1e-9 for actual, expected in zip(actual_bounds, expected_bounds)):
            raise ValueError("Output raster bounds do not match the computed grid.")
        if not dataset.profile.get("tiled", False):
            raise ValueError("Output raster is not tiled.")
        should_expect_overviews = require_overviews and max(dataset.width, dataset.height) > max(dataset.block_shapes[0])
        if should_expect_overviews:
            for band in dataset.indexes:
                if not dataset.overviews(band):
                    raise ValueError("Output COG does not expose internal overviews.")


def validate_stac(item_path: Path) -> None:
    item = pystac.Item.from_file(str(item_path))
    if "data" not in item.assets:
        raise ValueError("STAC item is missing the primary data asset.")
