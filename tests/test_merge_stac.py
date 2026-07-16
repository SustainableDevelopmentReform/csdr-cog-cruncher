from pathlib import Path

import pystac
from rasterio.crs import CRS

from csdr_cog_cruncher.grid import GridSpec
from csdr_cog_cruncher.stac import build_catalog
from scripts.merge_stac import merge


def _write_run(
    run_dir: Path,
    product_id: str,
    item_title: str,
    start: str,
    end: str,
    nominal: str,
) -> None:
    metadata = {
        "title": item_title,
        "collection_title": "Example observations",
        "collection_description": "A stable collection description.",
        "description": "One observation epoch.",
        "license": "CC-BY-4.0",
        "start_datetime": start,
        "end_datetime": end,
        "datetime": nominal,
        "gsd": 1.0,
        "bands": [{"name": "observation"}],
    }
    grid = GridSpec(
        crs_wkt=CRS.from_epsg(4326).to_wkt(),
        resolution=(1.0, 1.0),
        left=0.0,
        bottom=0.0,
        right=1.0,
        top=1.0,
        width=1,
        height=1,
    )
    build_catalog(
        output_dir=run_dir,
        product_id=product_id,
        data_path=run_dir / "mosaic.tif",
        grid=grid,
        collection_id="example-observations",
        product_metadata=metadata,
    )


def test_merge_preserves_epochs_and_uses_collection_title(tmp_path: Path) -> None:
    first = tmp_path / "first_run"
    second = tmp_path / "second_run"
    _write_run(
        first,
        "first-observation",
        "Observation alpha (not a year suffix)",
        "2019-01-01T00:00:00Z",
        "2020-12-31T23:59:59Z",
        "2020-01-01T00:00:00Z",
    )
    _write_run(
        second,
        "second-observation",
        "Observation beta (also not a year suffix)",
        "2023-01-01T00:00:00Z",
        "2024-12-31T23:59:59Z",
        "2024-01-01T00:00:00Z",
    )

    out_dir = tmp_path / "merged"
    merge(
        [first, second],
        out_dir,
        collection_id=None,
        title=None,
        description=None,
        https_base="https://example.test/products",
        s3_base="s3://example-products",
        validate=False,
    )

    catalog = pystac.Catalog.from_file(str(out_dir / "catalog.json"))
    collection = next(catalog.get_collections())
    assert collection.title == "Example observations (multi-temporal, 2019–2024)"
    assert len(collection.extent.temporal.intervals) == 3

    items = sorted(catalog.get_items(recursive=True), key=lambda item: item.id)
    assert [item.datetime.year for item in items] == [2020, 2024]
    assert all("start_datetime" not in item.properties for item in items)
    assert all("end_datetime" not in item.properties for item in items)
    assert items[0].assets["data"].href == (
        "https://example.test/products/first_run/mosaic.tif"
    )
    assert items[1].assets["data"].extra_fields["alternate"]["s3"]["href"] == (
        "s3://example-products/second_run/mosaic.tif"
    )
