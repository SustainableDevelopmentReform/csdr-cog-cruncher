"""STAC document creation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pystac
from rasterio.crs import CRS
from rasterio.warp import transform_bounds
from shapely.geometry import box, mapping

from csdr_cog_cruncher.grid import GridSpec
from csdr_cog_cruncher.metadata import ACA_COLLECTION_ID, aca_product_metadata


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def build_catalog(
    *,
    output_dir: Path,
    product_id: str,
    data_path: Path,
    grid: GridSpec,
    collection_id: str = ACA_COLLECTION_ID,
    product_metadata: dict[str, Any] | None = None,
    dtype: str = "uint8",
    asset_media_type: str | None = None,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = product_metadata or aca_product_metadata()
    source_crs = CRS.from_wkt(grid.crs_wkt)
    wgs84_bounds = transform_bounds(source_crs, "EPSG:4326", *grid.bounds, densify_pts=21)
    geometry = mapping(box(*wgs84_bounds))
    bbox = list(wgs84_bounds)
    start_datetime = metadata["start_datetime"]
    end_datetime = metadata["end_datetime"]
    start = _parse_timestamp(start_datetime)
    end = _parse_timestamp(end_datetime)
    bands = metadata["bands"]
    title = metadata["title"]
    description = metadata["description"]
    license_id = metadata["license"]

    item = pystac.Item(
        id=product_id,
        geometry=geometry,
        bbox=bbox,
        datetime=None,
        properties={
            "title": title,
            "description": description,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "gsd": metadata["gsd"],
            "providers": metadata.get("providers", []),
            "keywords": metadata.get("keywords", []),
            "license": license_id,
        },
    )
    item.stac_extensions = [
        "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
        "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
        "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    ]
    epsg = source_crs.to_epsg()
    if epsg is not None:
        item.properties["proj:epsg"] = epsg
    item.properties["proj:shape"] = [grid.height, grid.width]
    item.properties["proj:bbox"] = list(grid.bounds)
    item.properties["proj:transform"] = list(grid.transform_tuple())
    item.properties["eo:bands"] = bands
    if metadata.get("doi"):
        item.properties["sci:doi"] = metadata["doi"]
    if metadata.get("citation"):
        item.properties["sci:citation"] = metadata["citation"]

    is_cog = (asset_media_type or pystac.MediaType.COG) == pystac.MediaType.COG
    asset = pystac.Asset(
        href=data_path.resolve().as_uri(),
        media_type=asset_media_type or pystac.MediaType.COG,
        roles=["data"],
        title=f"Merged {title}",
        description=(
            f"Merged sparse {title} Cloud Optimized GeoTIFF."
            if is_cog
            else f"Merged sparse {title} GeoTIFF stage product."
        ),
        extra_fields={
            "eo:bands": bands,
            "raster:bands": [
                {
                    "data_type": dtype,
                    "spatial_resolution": metadata["gsd"],
                }
                for _ in bands
            ],
        },
    )
    item.add_asset("data", asset)
    for link_data in metadata.get("source_links", []):
        item.add_link(pystac.Link(rel=link_data["rel"], target=link_data["href"]))

    extent = pystac.Extent(
        spatial=pystac.SpatialExtent([bbox]),
        temporal=pystac.TemporalExtent([[start, end]]),
    )
    collection = pystac.Collection(
        id=collection_id,
        description=description,
        extent=extent,
        title=title,
        license=license_id,
    )
    collection.add_item(item)
    collection.extra_fields["providers"] = metadata.get("providers", [])
    collection.extra_fields["keywords"] = metadata.get("keywords", [])
    if metadata.get("doi"):
        collection.extra_fields["sci:doi"] = metadata["doi"]
    if metadata.get("citation"):
        collection.extra_fields["sci:citation"] = metadata["citation"]

    catalog = pystac.Catalog(
        id=f"{product_id}-catalog",
        description=f"Static STAC catalog for the merged {title} mosaic.",
        title=title,
    )
    catalog.add_child(collection)

    catalog.normalize_hrefs(str(output_dir))
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)

    catalog_path = output_dir / "catalog.json"
    collection_path = output_dir / collection_id / "collection.json"
    item_path = output_dir / collection_id / product_id / f"{product_id}.json"
    return catalog_path, collection_path, item_path
