"""Workflow orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import logging

import pystac

from csdr_cog_cruncher.config import WorkflowConfig
from csdr_cog_cruncher.grid import build_grid, write_grid
from csdr_cog_cruncher.inventory import scan_tiles, validate_inventory, write_inventory
from csdr_cog_cruncher.mosaic import build_vrt, convert_stage_to_cog, write_sparse_stage_mosaic
from csdr_cog_cruncher.metadata import validate_product_metadata
from csdr_cog_cruncher.stac import build_catalog
from csdr_cog_cruncher.validate import validate_raster, validate_stac


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkflowResult:
    inventory_path: Path
    grid_path: Path
    vrt_path: Path
    stage_path: Path
    data_path: Path
    catalog_path: Path | None
    collection_path: Path | None
    item_path: Path
    manifest_path: Path
    merge_stats: dict[str, Any]


def run_workflow(config: WorkflowConfig) -> WorkflowResult:
    config.output_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Scanning and validating source tiles: %s", config.input_glob)
    records = scan_tiles(config.input_glob)
    summary = validate_inventory(records)
    product_metadata = validate_product_metadata(config.product_metadata, summary.count)
    write_inventory(records, summary, config.inventory_path)

    LOGGER.info("Building output grid and VRT for %d tiles", len(records))
    grid = build_grid(records, extent_mode=config.extent_mode, global_bounds=config.global_bounds)
    write_grid(grid, config.grid_path)

    build_vrt(records, grid, summary, config.vrt_path, product_metadata["bands"])
    LOGGER.info("Writing sparse stage mosaic: %s", config.stage_path)
    merge_stats = write_sparse_stage_mosaic(
        records,
        grid,
        summary,
        config.stage_path,
        blocksize=config.blocksize,
        compression=config.compression,
        bigtiff=config.bigtiff,
        num_threads=config.num_threads,
        bands=product_metadata["bands"],
    )

    data_path = config.stage_path
    if not config.skip_cog:
        LOGGER.info("Converting stage mosaic to COG: %s", config.cog_path)
        convert_stage_to_cog(
            config.stage_path,
            config.cog_path,
            blocksize=config.blocksize,
            compression=config.compression,
            bigtiff=config.bigtiff,
            num_threads=config.num_threads,
            overview_resampling=config.overview_resampling,
        )
        data_path = config.cog_path

    catalog_path: Path | None = None
    collection_path: Path | None = None
    item_path = config.item_path
    if config.write_catalog:
        LOGGER.info("Writing static STAC catalog")
        catalog_path, collection_path, item_path = build_catalog(
            output_dir=config.output_dir,
            product_id=config.product_id,
            data_path=data_path,
            grid=grid,
            collection_id=config.collection_id,
            product_metadata=product_metadata,
            dtype=summary.dtype,
            asset_media_type=(
                pystac.MediaType.COG
                if not config.skip_cog
                else getattr(pystac.MediaType, "GEOTIFF", "image/tiff; application=geotiff")
            ),
        )

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": config.serializable_dict(),
        "inventory_path": str(config.inventory_path),
        "grid_path": str(config.grid_path),
        "vrt_path": str(config.vrt_path),
        "stage_path": str(config.stage_path),
        "data_path": str(data_path),
        "catalog_path": str(catalog_path) if catalog_path else None,
        "collection_path": str(collection_path) if collection_path else None,
        "item_path": str(item_path),
        "merge_stats": merge_stats.to_dict(),
    }
    with config.manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    if config.validate_outputs:
        LOGGER.info("Validating raster and STAC outputs")
        validate_raster(
            data_path,
            grid,
            summary,
            require_overviews=not config.skip_cog,
        )
        validate_stac(item_path)

    if not config.keep_stage and not config.skip_cog and config.stage_path.exists():
        config.stage_path.unlink()

    LOGGER.info("Workflow complete: %s", data_path)

    return WorkflowResult(
        inventory_path=config.inventory_path,
        grid_path=config.grid_path,
        vrt_path=config.vrt_path,
        stage_path=config.stage_path,
        data_path=data_path,
        catalog_path=catalog_path,
        collection_path=collection_path,
        item_path=item_path,
        manifest_path=config.manifest_path,
        merge_stats=merge_stats.to_dict(),
    )
