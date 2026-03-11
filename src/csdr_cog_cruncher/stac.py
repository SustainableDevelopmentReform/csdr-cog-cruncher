"""STAC document creation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pystac
from shapely.geometry import box, mapping

from csdr_cog_cruncher.grid import GridSpec
from csdr_cog_cruncher.metadata import (
    ACA_BANDS,
    ACA_COLLECTION_ID,
    ACA_END_DATETIME,
    ACA_KEYWORDS,
    ACA_LICENSE,
    ACA_PRODUCT_DESCRIPTION,
    ACA_PRODUCT_TITLE,
    ACA_PROVIDERS,
    ACA_SCI_CITATION,
    ACA_SCI_DOI,
    ACA_SOURCE_LINKS,
    ACA_START_DATETIME,
)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def build_catalog(
    *,
    output_dir: Path,
    product_id: str,
    data_path: Path,
    grid: GridSpec,
    collection_id: str = ACA_COLLECTION_ID,
    asset_media_type: str | None = None,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    geometry = mapping(box(*grid.bounds))
    bbox = list(grid.bounds)
    start = _parse_timestamp(ACA_START_DATETIME)
    end = _parse_timestamp(ACA_END_DATETIME)

    item = pystac.Item(
        id=product_id,
        geometry=geometry,
        bbox=bbox,
        datetime=None,
        properties={
            "title": ACA_PRODUCT_TITLE,
            "description": ACA_PRODUCT_DESCRIPTION,
            "start_datetime": ACA_START_DATETIME,
            "end_datetime": ACA_END_DATETIME,
            "gsd": 5.0,
            "providers": ACA_PROVIDERS,
            "keywords": ACA_KEYWORDS,
            "license": ACA_LICENSE,
            "sci:doi": ACA_SCI_DOI,
            "sci:citation": ACA_SCI_CITATION,
        },
    )
    item.stac_extensions = [
        "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
        "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
        "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
    ]
    item.properties["proj:epsg"] = 4326
    item.properties["proj:shape"] = [grid.height, grid.width]
    item.properties["proj:bbox"] = bbox
    item.properties["proj:transform"] = list(grid.transform_tuple())
    item.properties["eo:bands"] = ACA_BANDS

    is_cog = (asset_media_type or pystac.MediaType.COG) == pystac.MediaType.COG
    asset = pystac.Asset(
        href=data_path.resolve().as_uri(),
        media_type=asset_media_type or pystac.MediaType.COG,
        roles=["data"],
        title="Merged ACA habitat mosaic",
        description=(
            "Merged sparse ACA reef habitat mosaic Cloud Optimized GeoTIFF."
            if is_cog
            else "Merged sparse ACA reef habitat mosaic GeoTIFF stage product."
        ),
        extra_fields={
            "eo:bands": ACA_BANDS,
            "raster:bands": [
                {
                    "data_type": "uint8",
                    "bits_per_sample": 8,
                    "spatial_resolution": 5.0,
                }
                for _ in ACA_BANDS
            ],
        },
    )
    item.add_asset("data", asset)
    for link_data in ACA_SOURCE_LINKS:
        item.add_link(pystac.Link(rel=link_data["rel"], target=link_data["href"]))

    extent = pystac.Extent(
        spatial=pystac.SpatialExtent([bbox]),
        temporal=pystac.TemporalExtent([[start, end]]),
    )
    collection = pystac.Collection(
        id=collection_id,
        description=ACA_PRODUCT_DESCRIPTION,
        extent=extent,
        title=ACA_PRODUCT_TITLE,
        license=ACA_LICENSE,
    )
    collection.add_item(item)
    collection.extra_fields["providers"] = ACA_PROVIDERS
    collection.extra_fields["keywords"] = ACA_KEYWORDS
    collection.extra_fields["sci:doi"] = ACA_SCI_DOI
    collection.extra_fields["sci:citation"] = ACA_SCI_CITATION

    catalog = pystac.Catalog(
        id=f"{product_id}-catalog",
        description="Static STAC catalog for the merged ACA habitat mosaic.",
        title=ACA_PRODUCT_TITLE,
    )
    catalog.add_child(collection)

    catalog.normalize_hrefs(str(output_dir))
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)

    catalog_path = output_dir / "catalog.json"
    collection_path = output_dir / collection_id / "collection.json"
    item_path = output_dir / collection_id / product_id / f"{product_id}.json"
    return catalog_path, collection_path, item_path
