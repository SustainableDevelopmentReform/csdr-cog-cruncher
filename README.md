# csdr-cog-cruncher

`csdr-cog-cruncher` is a Python tool for combining many tiled GeoTIFF or COG
inputs into one sparse mosaic, then writing a STAC description for the result.
It is aimed at large, sparse rasters where a naive dense merge would be too
expensive in memory or disk.

The current worked example in this repository is the Allen Coral Atlas reef
habitat tiles exported from Google Earth Engine.

## What It Does

The workflow:

- scans and inventories input raster tiles
- validates CRS, resolution, dtype, band count, and grid alignment
- computes an output extent
- builds a VRT mosaic
- writes a sparse staged GeoTIFF by copying only non-zero blocks
- optionally converts the stage product into a COG
- writes a static STAC catalog, collection, and item

This makes it suitable for wide but sparse rasters where most output blocks are
empty.

## Install

```bash
python3 -m pip install -e .
```

## General Usage

Run with a custom glob and output directory:

```bash
csdr-cog-cruncher --input-glob '/path/to/tiles/*.tif' --output-dir /path/to/output
```

Useful options:

- `--extent-mode union` to build the mosaic over the combined bounds of all input tiles
- `--extent-mode global` to use configured global bounds
- `--skip-cog` to stop after building the sparse staged GeoTIFF
- `--keep-stage` to preserve the staged GeoTIFF after COG conversion

You can also run from config:

```bash
csdr-cog-cruncher --config configs/workflow.example.yaml
```

## Worked Example: Allen Coral Atlas

Stage-only run against the sample tiles:

```bash
csdr-cog-cruncher --input-glob 'gee_tiles/*.tif' --output-dir outputs/sample_stage --skip-cog --keep-stage
```

Full run from the bundled example config:

```bash
csdr-cog-cruncher --config configs/workflow.example.yaml
```

The ACA sample tiles in [`gee_tiles/`](/gee_tiles) are the current development fixture for the workflow.

## Outputs

Each run writes:

- `inventory.json`
- `grid.json`
- `mosaic.vrt`
- `mosaic_stage.tif`
- `mosaic.tif` when COG conversion is enabled
- `catalog.json`, `collection.json`, and the STAC Item JSON

## Current Scope

The raster merge logic is general-purpose, but the bundled STAC metadata profile
is currently tailored to the Allen Coral Atlas worked example in
[`metadata.py`](/metadata.py).
For other datasets, the merge pipeline is reusable as-is, but the metadata
module should be adapted so titles, providers, temporal fields, keywords, and
band descriptions match the new source data.

## Notes

- The merge step copies source tiles block-by-block and skips all-zero blocks.
- `extent_mode: union` uses the combined bounding box of all input tiles.
- The stage GeoTIFF path is the safest benchmark target for very sparse, very wide extents.
