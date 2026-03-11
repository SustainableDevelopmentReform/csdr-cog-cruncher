from pathlib import Path

from csdr_cog_cruncher.inventory import scan_tiles, validate_inventory


def test_scan_tiles_reads_sample_metadata() -> None:
    records = scan_tiles("gee_tiles/*.tif")
    summary = validate_inventory(records)

    assert len(records) == 3
    assert summary.count == 3
    assert summary.dtype == "uint8"
    assert summary.tile_count == 3
    assert Path(records[0].path).suffix == ".tif"
