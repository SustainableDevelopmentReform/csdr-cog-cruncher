"""VRT construction and sparse mosaic writing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from rasterio.shutil import copy as rio_copy
from rasterio.windows import Window

from csdr_cog_cruncher.grid import GridSpec, tile_window
from csdr_cog_cruncher.inventory import InventorySummary, TileRecord


LOGGER = logging.getLogger(__name__)


VRT_DATA_TYPE_BY_DTYPE = {
    "uint8": "Byte",
}


@dataclass(slots=True)
class MergeStats:
    tile_count: int
    total_source_blocks: int
    written_blocks: int
    skipped_zero_blocks: int
    nonzero_pixels_written: int

    def to_dict(self) -> dict[str, int]:
        return {
            "tile_count": self.tile_count,
            "total_source_blocks": self.total_source_blocks,
            "written_blocks": self.written_blocks,
            "skipped_zero_blocks": self.skipped_zero_blocks,
            "nonzero_pixels_written": self.nonzero_pixels_written,
        }


def build_vrt(
    records: list[TileRecord],
    grid: GridSpec,
    summary: InventorySummary,
    path: Path,
    bands: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    vrt_dataset = ET.Element(
        "VRTDataset",
        rasterXSize=str(grid.width),
        rasterYSize=str(grid.height),
    )
    srs = ET.SubElement(vrt_dataset, "SRS")
    srs.text = summary.crs_wkt
    geotransform = ET.SubElement(vrt_dataset, "GeoTransform")
    geotransform.text = ", ".join(str(value) for value in grid.transform_tuple())

    data_type = VRT_DATA_TYPE_BY_DTYPE.get(summary.dtype)
    if data_type is None:
        raise ValueError(f"Unsupported VRT data type mapping for dtype={summary.dtype!r}")

    for band_index in range(1, summary.count + 1):
        band_meta = bands[band_index - 1]
        raster_band = ET.SubElement(
            vrt_dataset,
            "VRTRasterBand",
            dataType=data_type,
            band=str(band_index),
            subClass="VRTSourcedRasterBand",
        )
        description = ET.SubElement(raster_band, "Description")
        description.text = band_meta["name"]
        if summary.nodata is not None:
            nodata_value = ET.SubElement(raster_band, "NoDataValue")
            nodata_value.text = str(summary.nodata)

        for record in records:
            dst_window = tile_window(grid, record)
            source = ET.SubElement(raster_band, "SimpleSource")
            source_filename = ET.SubElement(source, "SourceFilename", relativeToVRT="0")
            source_filename.text = str(record.path)
            source_band = ET.SubElement(source, "SourceBand")
            source_band.text = str(band_index)
            if summary.nodata is not None:
                source_nodata = ET.SubElement(source, "NODATA")
                source_nodata.text = str(summary.nodata)
            src_rect = ET.SubElement(
                source,
                "SrcRect",
                xOff="0",
                yOff="0",
                xSize=str(record.width),
                ySize=str(record.height),
            )
            dst_rect = ET.SubElement(
                source,
                "DstRect",
                xOff=str(int(dst_window.col_off)),
                yOff=str(int(dst_window.row_off)),
                xSize=str(record.width),
                ySize=str(record.height),
            )
            src_rect.tail = "\n"
            dst_rect.tail = "\n"

    ET.indent(vrt_dataset, space="  ")
    tree = ET.ElementTree(vrt_dataset)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def write_sparse_stage_mosaic(
    records: list[TileRecord],
    grid: GridSpec,
    summary: InventorySummary,
    path: Path,
    *,
    blocksize: int,
    compression: str,
    bigtiff: str,
    num_threads: str,
    bands: list[dict[str, object]],
) -> MergeStats:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "width": grid.width,
        "height": grid.height,
        "count": summary.count,
        "dtype": summary.dtype,
        "crs": summary.crs_wkt,
        "transform": grid.transform,
        "tiled": True,
        "blockxsize": blocksize,
        "blockysize": blocksize,
        "compress": compression,
        "interleave": "pixel",
        "BIGTIFF": bigtiff,
        "NUM_THREADS": num_threads,
        "SPARSE_OK": True,
    }
    if summary.nodata is not None:
        profile["nodata"] = summary.nodata

    total_source_blocks = 0
    written_blocks = 0
    skipped_zero_blocks = 0
    nonzero_pixels_written = 0

    with rasterio.open(path, "w", **profile) as destination:
        for band_index, band_meta in enumerate(bands, start=1):
            destination.set_band_description(band_index, band_meta["name"])

        for tile_index, record in enumerate(records, start=1):
            LOGGER.info("Merging tile %d/%d: %s", tile_index, len(records), record.name)
            destination_window = tile_window(grid, record)
            with rasterio.open(record.path) as source:
                for _, src_window in source.block_windows(1):
                    total_source_blocks += 1
                    block = source.read(window=src_window)
                    nonzero = int(np.count_nonzero(block))
                    if nonzero == 0:
                        skipped_zero_blocks += 1
                        continue

                    nonzero_pixels_written += nonzero
                    dst_window = Window(
                        col_off=int(destination_window.col_off) + int(src_window.col_off),
                        row_off=int(destination_window.row_off) + int(src_window.row_off),
                        width=int(src_window.width),
                        height=int(src_window.height),
                    )
                    destination.write(block, window=dst_window)
                    written_blocks += 1

    return MergeStats(
        tile_count=len(records),
        total_source_blocks=total_source_blocks,
        written_blocks=written_blocks,
        skipped_zero_blocks=skipped_zero_blocks,
        nonzero_pixels_written=nonzero_pixels_written,
    )


def convert_stage_to_cog(
    stage_path: Path,
    cog_path: Path,
    *,
    blocksize: int,
    compression: str,
    bigtiff: str,
    num_threads: str,
    overview_resampling: str,
) -> None:
    cog_path.parent.mkdir(parents=True, exist_ok=True)
    rio_copy(
        stage_path,
        cog_path,
        driver="COG",
        BLOCKSIZE=blocksize,
        COMPRESS=compression,
        BIGTIFF=bigtiff,
        NUM_THREADS=num_threads,
        OVERVIEW_RESAMPLING=overview_resampling.upper(),
    )
