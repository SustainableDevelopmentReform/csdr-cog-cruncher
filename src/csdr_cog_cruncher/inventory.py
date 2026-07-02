"""Tile inventory and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Any
import json

import rasterio
from rasterio.coords import BoundingBox


@dataclass(slots=True)
class TileRecord:
    path: Path
    name: str
    fingerprint: str
    crs_wkt: str
    transform: tuple[float, float, float, float, float, float]
    resolution: tuple[float, float]
    width: int
    height: int
    count: int
    dtype: str
    nodata: float | None
    bounds: tuple[float, float, float, float]
    compression: str | None
    block_shapes: list[tuple[int, int]]

    @property
    def left(self) -> float:
        return self.bounds[0]

    @property
    def bottom(self) -> float:
        return self.bounds[1]

    @property
    def right(self) -> float:
        return self.bounds[2]

    @property
    def top(self) -> float:
        return self.bounds[3]

    @property
    def block_shape(self) -> tuple[int, int]:
        return self.block_shapes[0]

    def bounds_box(self) -> BoundingBox:
        return BoundingBox(*self.bounds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "name": self.name,
            "fingerprint": self.fingerprint,
            "crs_wkt": self.crs_wkt,
            "transform": list(self.transform),
            "resolution": list(self.resolution),
            "width": self.width,
            "height": self.height,
            "count": self.count,
            "dtype": self.dtype,
            "nodata": self.nodata,
            "bounds": list(self.bounds),
            "compression": self.compression,
            "block_shapes": [list(shape) for shape in self.block_shapes],
        }


@dataclass(slots=True)
class InventorySummary:
    crs_wkt: str
    dtype: str
    count: int
    resolution: tuple[float, float]
    nodata: float | None
    tile_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "crs_wkt": self.crs_wkt,
            "dtype": self.dtype,
            "count": self.count,
            "resolution": list(self.resolution),
            "nodata": self.nodata,
            "tile_count": self.tile_count,
        }


def _fingerprint_from_stat(path: Path) -> str:
    stat = path.stat()
    return f"stat:{stat.st_size}:{stat.st_mtime_ns}"


def scan_tiles(input_glob: str) -> list[TileRecord]:
    paths = [Path(path) for path in sorted(glob(input_glob))]
    if not paths:
        raise FileNotFoundError(f"No tiles matched input_glob={input_glob!r}")

    records: list[TileRecord] = []
    for path in paths:
        with rasterio.open(path) as dataset:
            if len(set(dataset.dtypes)) != 1:
                raise ValueError(f"Mixed band dtypes are not supported in {path.name}")
            if len(set(dataset.nodatavals)) != 1:
                raise ValueError(f"Mixed band nodata values are not supported in {path.name}")
            transform = dataset.transform
            record = TileRecord(
                path=path.resolve(),
                name=path.name,
                fingerprint=_fingerprint_from_stat(path),
                crs_wkt=dataset.crs.to_wkt(),
                transform=(transform.a, transform.b, transform.c, transform.d, transform.e, transform.f),
                resolution=(float(dataset.res[0]), float(dataset.res[1])),
                width=dataset.width,
                height=dataset.height,
                count=dataset.count,
                dtype=dataset.dtypes[0],
                nodata=dataset.nodatavals[0],
                bounds=(
                    float(dataset.bounds.left),
                    float(dataset.bounds.bottom),
                    float(dataset.bounds.right),
                    float(dataset.bounds.top),
                ),
                compression=str(dataset.compression).split(".")[-1] if dataset.compression else None,
                block_shapes=[(int(rows), int(cols)) for rows, cols in dataset.block_shapes],
            )
        records.append(record)
    return records


def validate_inventory(records: list[TileRecord], tolerance: float = 1e-9) -> InventorySummary:
    if not records:
        raise ValueError("Inventory is empty.")

    first = records[0]
    crs_wkt = first.crs_wkt
    dtype = first.dtype
    count = first.count
    resolution = first.resolution
    nodata = first.nodata
    origin_left = first.left
    origin_top = first.top

    windows: list[tuple[int, int, int, int, str]] = []
    for record in records:
        if record.crs_wkt != crs_wkt:
            raise ValueError(f"CRS mismatch for {record.name}")
        if record.dtype != dtype:
            raise ValueError(f"Dtype mismatch for {record.name}")
        if record.count != count:
            raise ValueError(f"Band count mismatch for {record.name}")
        if record.nodata != nodata:
            raise ValueError(f"Nodata mismatch for {record.name}")

        if abs(record.resolution[0] - resolution[0]) > tolerance or abs(record.resolution[1] - resolution[1]) > tolerance:
            raise ValueError(f"Resolution mismatch for {record.name}")

        col_offset = (record.left - origin_left) / resolution[0]
        row_offset = (origin_top - record.top) / resolution[1]
        if abs(col_offset - round(col_offset)) > tolerance or abs(row_offset - round(row_offset)) > tolerance:
            raise ValueError(f"Grid alignment mismatch for {record.name}")

        tile_window = (
            int(round(col_offset)),
            int(round(row_offset)),
            int(round(col_offset)) + record.width,
            int(round(row_offset)) + record.height,
            record.name,
        )
        windows.append(tile_window)

    for index, left_window in enumerate(windows):
        for right_window in windows[index + 1 :]:
            if _windows_overlap(left_window, right_window):
                raise ValueError(
                    f"Overlapping source tiles detected: {left_window[4]} and {right_window[4]}"
                )

    return InventorySummary(
        crs_wkt=crs_wkt,
        dtype=dtype,
        count=count,
        resolution=resolution,
        nodata=nodata,
        tile_count=len(records),
    )


def _windows_overlap(left_window: tuple[int, int, int, int, str], right_window: tuple[int, int, int, int, str]) -> bool:
    left, top, right, bottom, _ = left_window
    other_left, other_top, other_right, other_bottom, _ = right_window
    return not (
        right <= other_left
        or other_right <= left
        or bottom <= other_top
        or other_bottom <= top
    )


def write_inventory(records: list[TileRecord], summary: InventorySummary, path: Path) -> None:
    payload = {
        "summary": summary.to_dict(),
        "tiles": [record.to_dict() for record in records],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
