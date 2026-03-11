from pathlib import Path

import numpy as np
import pystac
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
