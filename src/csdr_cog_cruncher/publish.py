"""Where built outputs are published, and how their assets are addressed there.

A run writes its COG next to its catalog on the build machine, so the natural asset href is a
local ``file://`` path - which is useless to anyone reading the catalog afterwards, and leaks the
build machine's directory layout. Every catalog we publish therefore addresses its data by the
public URL the COG is synced to, with the ``s3://`` URI offered as an alternate for in-region
readers.

Both the per-run catalogs and the merged multi-temporal catalog publish the same way, so the
rules live here rather than in either one.
"""

from __future__ import annotations

import pystac

# Each run's data asset resolves to ``{base}/{run_dir_name}/{filename}`` -- matching the bucket
# layout the outputs are synced into.
DEFAULT_HTTPS_BASE = (
    "https://csdr-public-datasets.s3.ap-southeast-2.amazonaws.com/cog-cruncher-outputs"
)
DEFAULT_S3_BASE = "s3://csdr-public-datasets/cog-cruncher-outputs"

ALTERNATE_ASSETS_EXT = (
    "https://stac-extensions.github.io/alternate-assets/v1.2.0/schema.json"
)


def set_published_asset(
    item: pystac.Item,
    run_name: str,
    https_base: str = DEFAULT_HTTPS_BASE,
    s3_base: str | None = DEFAULT_S3_BASE,
) -> None:
    """Point the item's data asset at its published location and add an s3 alternate.

    The filename is taken from the asset's current href, so this is safe to apply to an item
    whose asset is still local, and re-applying it to an already-published item is a no-op.
    """
    asset = item.assets["data"]
    filename = asset.href.rstrip("/").rsplit("/", 1)[-1]
    asset.href = f"{https_base.rstrip('/')}/{run_name}/{filename}"
    if s3_base:
        asset.extra_fields["alternate"] = {
            "s3": {
                "href": f"{s3_base.rstrip('/')}/{run_name}/{filename}",
                "title": "S3 access",
            }
        }
        if ALTERNATE_ASSETS_EXT not in item.stac_extensions:
            item.stac_extensions.append(ALTERNATE_ASSETS_EXT)
    else:
        alternates = asset.extra_fields.get("alternate", {})
        alternates.pop("s3", None)
        if alternates:
            asset.extra_fields["alternate"] = alternates
        else:
            asset.extra_fields.pop("alternate", None)
            if ALTERNATE_ASSETS_EXT in item.stac_extensions:
                item.stac_extensions.remove(ALTERNATE_ASSETS_EXT)
