from dataclasses import replace
from pathlib import Path

import pytest

from csdr_cog_cruncher.inventory import scan_tiles, validate_inventory


def test_scan_tiles_reads_sample_metadata() -> None:
    records = scan_tiles("gee_tiles/*.tif")
    summary = validate_inventory(records)

    assert len(records) == 3
    assert summary.count == 3
    assert summary.dtype == "uint8"
    assert summary.tile_count == 3
    assert Path(records[0].path).suffix == ".tif"


def test_validate_inventory_allows_subpixel_coordinate_roundoff() -> None:
    records = scan_tiles("gee_tiles/*.tif")[:2]
    resolution = records[0].resolution[0]
    shifted_bounds = list(records[1].bounds)
    shifted_bounds[0] += resolution * 1e-8
    shifted_bounds[2] += resolution * 1e-8
    records[1] = replace(records[1], bounds=tuple(shifted_bounds))

    summary = validate_inventory(records)

    assert summary.tile_count == 2


def test_validate_inventory_rejects_material_grid_misalignment() -> None:
    records = scan_tiles("gee_tiles/*.tif")[:2]
    resolution = records[0].resolution[0]
    shifted_bounds = list(records[1].bounds)
    shifted_bounds[0] += resolution * 1e-4
    shifted_bounds[2] += resolution * 1e-4
    records[1] = replace(records[1], bounds=tuple(shifted_bounds))

    with pytest.raises(ValueError, match="Grid alignment mismatch"):
        validate_inventory(records)
