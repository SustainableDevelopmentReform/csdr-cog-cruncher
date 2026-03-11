"""Output grid definition and tile placement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

from rasterio.transform import Affine
from rasterio.windows import Window

from csdr_cog_cruncher.inventory import TileRecord


@dataclass(slots=True)
class GridSpec:
    crs_wkt: str
    resolution: tuple[float, float]
    left: float
    bottom: float
    right: float
    top: float
    width: int
    height: int

    @property
    def transform(self) -> Affine:
        return Affine(self.resolution[0], 0.0, self.left, 0.0, -self.resolution[1], self.top)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.left, self.bottom, self.right, self.top)

    def transform_tuple(self) -> tuple[float, float, float, float, float, float]:
        affine = self.transform
        return (affine.a, affine.b, affine.c, affine.d, affine.e, affine.f)

    def to_dict(self) -> dict[str, Any]:
        return {
            "crs_wkt": self.crs_wkt,
            "resolution": list(self.resolution),
            "bounds": list(self.bounds),
            "width": self.width,
            "height": self.height,
            "transform": list(self.transform_tuple()),
        }


def build_grid(
    records: list[TileRecord],
    extent_mode: str = "union",
    global_bounds: tuple[float, float, float, float] | None = None,
) -> GridSpec:
    if not records:
        raise ValueError("Cannot build a grid from an empty inventory.")

    crs_wkt = records[0].crs_wkt
    resolution = records[0].resolution

    if extent_mode == "global":
        if global_bounds is None:
            raise ValueError("global_bounds are required when extent_mode='global'.")
        left, bottom, right, top = global_bounds
    elif extent_mode == "union":
        left = min(record.left for record in records)
        bottom = min(record.bottom for record in records)
        right = max(record.right for record in records)
        top = max(record.top for record in records)
    else:
        raise ValueError(f"Unsupported extent_mode={extent_mode!r}")

    width = int(round((right - left) / resolution[0]))
    height = int(round((top - bottom) / resolution[1]))
    snapped_right = left + width * resolution[0]
    snapped_bottom = top - height * resolution[1]
    return GridSpec(
        crs_wkt=crs_wkt,
        resolution=resolution,
        left=left,
        bottom=snapped_bottom,
        right=snapped_right,
        top=top,
        width=width,
        height=height,
    )


def tile_window(grid: GridSpec, record: TileRecord) -> Window:
    col_off = int(round((record.left - grid.left) / grid.resolution[0]))
    row_off = int(round((grid.top - record.top) / grid.resolution[1]))
    return Window(col_off=col_off, row_off=row_off, width=record.width, height=record.height)


def write_grid(grid: GridSpec, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(grid.to_dict(), handle, indent=2)
