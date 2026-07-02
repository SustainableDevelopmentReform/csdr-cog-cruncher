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

For SSH and workstation use, the generic launcher bootstraps a local `.venv`
when necessary and forwards all arguments to the CLI:

```bash
./scripts/run_workflow.sh \
  --config configs/workflow.example.yaml \
  --input-glob '/data/tiles/*.tif' \
  --output-dir /data/output
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

## Worked Example: Global Seagrass

The second profile uses the 2023-2024 layer from the
[Global 10-meter seagrass maps](https://zenodo.org/records/18612240) dataset.
Run the bundled sample tiles with:

```bash
./scripts/run_workflow.sh --config configs/seagrass-2023-2024.yaml
```

On the workstation, pass the full tile directory and output directory:

```bash
./scripts/run_workflow.sh \
  --config configs/seagrass-2023-2024.yaml \
  --input-glob '/data/seagrass_tiles/*.tif' \
  --output-dir /data/seagrass_2023_2024
```

The launcher uses an 8 GB GDAL cache by default. Thread count, compression,
block size, Python interpreter, and stage-only operation can be overridden:

```bash
GDAL_CACHEMAX=16384 ./scripts/run_workflow.sh --config configs/seagrass-2023-2024.yaml
PYTHON=/path/to/python ./scripts/run_workflow.sh --config configs/seagrass-2023-2024.yaml
./scripts/run_workflow.sh --config configs/seagrass-2023-2024.yaml \
  --num-threads ALL_CPUS --compression ZSTD --blocksize 512
./scripts/run_workflow.sh --config configs/seagrass-2023-2024.yaml \
  --skip-cog --keep-stage
```

The pipeline is CPU-based; the GPU is not used by GDAL's GeoTIFF/COG codecs.

## Outputs

Each run writes:

- `inventory.json`
- `grid.json`
- `mosaic.vrt`
- `mosaic_stage.tif`
- `mosaic.tif` when COG conversion is enabled
- `catalog.json`, `collection.json`, and the STAC Item JSON

## Product Profiles

Dataset-specific STAC metadata and band descriptions are supplied through the
`product_metadata` section of a workflow config. Bundled profiles are in
[`configs/workflow.example.yaml`](/configs/workflow.example.yaml) and
[`configs/seagrass-2023-2024.yaml`](/configs/seagrass-2023-2024.yaml).

The current sparse writer assumes zero-valued pixels are background. Inputs must
share a CRS, resolution, dtype, band count, nodata value, and pixel grid, and
tiles must not overlap. The VRT dtype mapping currently supports `uint8`.

## Notes

- The merge step copies source tiles block-by-block and skips all-zero blocks.
- `extent_mode: union` uses the combined bounding box of all input tiles.
- The stage GeoTIFF path is the safest benchmark target for very sparse, very wide extents.
