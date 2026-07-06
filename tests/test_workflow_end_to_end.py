import json
from pathlib import Path

import numpy as np
import pystac
import pytest
import rasterio
from rasterio.transform import Affine

from csdr_cog_cruncher.config import WorkflowConfig
from csdr_cog_cruncher.workflow import run_workflow


def _write_tile(path: Path, transform: Affine, values: tuple[int, int, int]) -> None:
    data = np.zeros((3, 64, 64), dtype=np.uint8)
    data[0, 8:24, 8:24] = values[0]
    data[1, 16:32, 12:28] = values[1]
    data[2, 4:20, 20:36] = values[2]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=64,
        height=64,
        count=3,
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
        tiled=True,
        blockxsize=16,
        blockysize=16,
        compress="LZW",
    ) as dataset:
        dataset.write(data)


def test_workflow_builds_sparse_mosaic_and_stac(tmp_path: Path) -> None:
    source_dir = tmp_path / "tiles"
    source_dir.mkdir()
    output_dir = tmp_path / "output"

    transform_a = Affine(0.01, 0.0, 0.0, 0.0, -0.01, 1.0)
    transform_b = Affine(0.01, 0.0, 0.96, 0.0, -0.01, 1.0)
    _write_tile(source_dir / "tile_a.tif", transform_a, (11, 12, 1))
    _write_tile(source_dir / "tile_b.tif", transform_b, (15, 18, 1))

    config = WorkflowConfig(
        input_glob=str(source_dir / "*.tif"),
        output_dir=output_dir,
        keep_stage=True,
        compression="LZW",
    )
    result = run_workflow(config)

    assert result.inventory_path.exists()
    assert result.grid_path.exists()
    assert result.vrt_path.exists()
    assert result.data_path.exists()
    assert result.item_path.exists()
    assert result.item_path == config.item_path
    assert result.completion_path.exists()

    with result.completion_path.open(encoding="utf-8") as handle:
        completion = json.load(handle)
    assert completion["status"] == "complete"
    assert completion["data_path"] == str(result.data_path)

    with rasterio.open(result.data_path) as dataset:
        assert dataset.width == 160
        assert dataset.height == 64
        left_window = dataset.read(window=((8, 24), (8, 24)))
        right_window = dataset.read(window=((8, 24), (104, 120)))
        gap_window = dataset.read(window=((8, 24), (72, 88)))
        assert np.max(left_window[0]) == 11
        assert np.max(right_window[0]) == 15
        assert np.count_nonzero(gap_window) == 0

    item = pystac.Item.from_file(str(result.item_path))
    assert item.id == config.product_id
    assert "data" in item.assets


def test_workflow_supports_one_band_product_metadata_and_nodata(tmp_path: Path) -> None:
    source_dir = tmp_path / "tiles"
    source_dir.mkdir()
    output_dir = tmp_path / "output"
    tile_path = source_dir / "seagrass.tif"
    data = np.zeros((1, 32, 32), dtype=np.uint8)
    data[0, 4:12, 8:16] = 1
    with rasterio.open(
        tile_path,
        "w",
        driver="GTiff",
        width=32,
        height=32,
        count=1,
        dtype="uint8",
        nodata=0,
        crs="EPSG:4326",
        transform=Affine(0.001, 0.0, 150.0, 0.0, -0.001, -30.0),
        tiled=True,
        blockxsize=16,
        blockysize=16,
    ) as dataset:
        dataset.write(data)

    metadata = {
        "title": "Test seagrass map",
        "description": "One-band test product.",
        "license": "CC-BY-4.0",
        "start_datetime": "2023-01-01T00:00:00Z",
        "end_datetime": "2024-12-31T23:59:59Z",
        "gsd": 10.0,
        "doi": "10.5281/zenodo.18612240",
        "bands": [{"name": "seagrass", "description": "Binary seagrass extent."}],
    }
    config = WorkflowConfig(
        input_glob=str(source_dir / "*.tif"),
        output_dir=output_dir,
        product_id="test-seagrass",
        collection_id="test-seagrass-collection",
        product_metadata=metadata,
        skip_cog=True,
        keep_stage=True,
        blocksize=16,
    )
    result = run_workflow(config)

    with rasterio.open(result.data_path) as dataset:
        assert dataset.count == 1
        assert dataset.nodata == 0
        assert dataset.descriptions == ("seagrass",)
        assert np.array_equal(dataset.read(), data)

    item = pystac.Item.from_file(str(result.item_path))
    assert item.properties["title"] == "Test seagrass map"
    assert item.properties["sci:doi"] == "10.5281/zenodo.18612240"
    assert item.properties["eo:bands"][0]["name"] == "seagrass"
    assert result.completion_path.exists()


def test_failed_rerun_removes_stale_completion_marker(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    config = WorkflowConfig(
        input_glob=str(tmp_path / "missing" / "*.tif"),
        output_dir=output_dir,
    )
    config.completion_path.write_text('{"status": "complete"}', encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="No tiles matched"):
        run_workflow(config)

    assert not config.completion_path.exists()
