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

Choose a product profile, then optionally override its input and output paths:

```bash
csdr-cog-cruncher --config configs/workflow.example.yaml \
  --input-glob '/path/to/tiles/*.tif' --output-dir /path/to/output
```

A config is required because every product must explicitly declare its
`product_id`, `collection_id`, and `product_metadata`; there is no implicit ACA
profile in the generic Python code.

Useful options:

- `--extent-mode union` to build the mosaic over the combined bounds of all input tiles
- `--extent-mode global` to use configured global bounds
- `--skip-cog` to stop after building the sparse staged GeoTIFF
- `--keep-stage` to preserve the staged GeoTIFF after COG conversion

To use all paths and settings from a config:

```bash
csdr-cog-cruncher --config configs/workflow.example.yaml
```

To see the exact output paths without starting any processing:

```bash
csdr-cog-cruncher --config configs/aca-workstation.yaml --show-outputs
```

For SSH and workstation use, the generic launcher bootstraps a local `.venv`
when necessary and forwards all arguments to the CLI:

```bash
./scripts/run_workflow.sh \
  --config configs/workflow.example.yaml \
  --input-glob '/data/tiles/*.tif' \
  --output-dir /data/output
```

For a long SSH run, add `--detach`. The launcher uses `nohup`, redirects output
to a log, and prints the expected output paths, background process ID, and
monitoring command. The run continues if the SSH session disconnects:

```bash
./scripts/run_workflow.sh --detach --config configs/seagrass-2023-2024.yaml
```

Logs are written to `logs/workflow-<timestamp>.log` by default. Use
`--log-file` to choose a path:

```bash
./scripts/run_workflow.sh --detach --log-file logs/aca.log \
  --config configs/aca-workstation.yaml
```

To submit both workstation products as independent background jobs:

```bash
./scripts/run_workstation_products.sh
```

This starts ACA reef and seagrass concurrently, gives each a timestamped log,
and returns control to the shell after both jobs are submitted. Each process
uses an 8 GB GDAL cache and `ALL_CPUS` by default. On a smaller workstation,
cap both jobs when submitting them:

```bash
GDAL_CACHEMAX=4096 WORKFLOW_NUM_THREADS=8 ./scripts/run_workstation_products.sh
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
- `build-manifest.json`
- `workflow-complete.json`, written last and only after validation succeeds

The stage file is removed after COG conversion unless `keep_stage` is enabled.
The STAC collection and item are stored below collection/product subdirectories;
the output plan printed at launch shows their exact paths.

Use the completion marker rather than the presence of `mosaic.tif` to decide
whether a run finished successfully. A raster can exist while it is still being
written. For the two workstation profiles:

```bash
test -f outputs/aca_reef_habitat_v2_0/workflow-complete.json && echo "ACA complete"
test -f outputs/seagrass_2023_2024/workflow-complete.json && echo "Seagrass complete"
```

The marker is removed when a new run starts, so a failed or active rerun cannot
be mistaken for a completed one.

The STAC Item's data asset is written with the public HTTPS URL as its primary
href and an `s3://` alternate, rather than a path on the build machine. Override
the defaults per profile with `href_base` and `s3_base` (set `s3_base: null` to
disable the alternate).

## Rebuilding and Merging STAC

STAC can be rebuilt from an existing run's `grid.json` and `mosaic.tif` without
re-running the expensive mosaic step:

```bash
.venv/bin/python scripts/rebuild_catalog.py \
  --config configs/seagrass-2019-2020.yaml \
  --run outputs/seagrass_2019_2020
```

Combine independently indexable epochs into one multi-temporal collection with
one Item per epoch:

```bash
.venv/bin/python scripts/merge_stac.py \
  outputs/seagrass_2019_2020 outputs/seagrass_2023_2024 \
  --config configs/seagrass-2023-2024.yaml \
  --out outputs/seagrass_multitemporal
```

Published Items contain one representative `datetime` and no item-level
`start_datetime`/`end_datetime`. The true coverage remains in the Collection's
temporal extent, including the overall span and each epoch. The representative
instant defaults to the span midpoint and can be set exactly with
`product_metadata.datetime`.

## Product Profiles

Dataset-specific STAC metadata and band descriptions are supplied through the
required `product_metadata` section of a workflow config. `collection_title`
and `collection_description` can provide stable collection-level text when Item
titles vary by epoch. Bundled profiles are in [`configs/`](/configs).

The current sparse writer assumes zero-valued pixels are background. Inputs must
share a CRS, resolution, dtype, band count, nodata value, and pixel grid, and
tiles must not overlap. The VRT dtype mapping currently supports `uint8`.

## Notes

- The merge step copies source tiles block-by-block and skips all-zero blocks.
- `extent_mode: union` uses the combined bounding box of all input tiles.
- The stage GeoTIFF path is the safest benchmark target for very sparse, very wide extents.
