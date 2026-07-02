"""Product metadata profiles and validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

ACA_COLLECTION_ID = "ACA/reef_habitat/v2_0"
ACA_PRODUCT_TITLE = (
    "Allen Coral Atlas (ACA) - Geomorphic Zonation and Benthic Habitat - v2.0"
)
ACA_PRODUCT_DESCRIPTION = (
    "Global Allen Coral Atlas shallow coral reef habitat layers composed of "
    "geomorphic zonation, benthic habitat, and reef extent classes at 5 m nominal "
    "resolution. This derivative product merges sparse source tiles into one "
    "Cloud Optimized GeoTIFF for workstation-scale analysis."
)
ACA_LICENSE = "CC-BY-4.0"
ACA_KEYWORDS = [
    "coral",
    "ocean",
    "planet_derived",
    "reef",
    "seagrass",
    "sentinel2_derived",
]
ACA_PROVIDERS = [
    {
        "name": "Allen Coral Atlas Partnership (ACA)",
        "roles": ["producer"],
        "url": "https://allencoralatlas.org/",
    },
    {
        "name": "University of Queensland (UQ)",
        "roles": ["licensor", "producer"],
        "url": "https://www.uq.edu.au/",
    },
    {
        "name": "Arizona State University Center for Global Discovery and Conservation Science (ASU GDCS)",
        "roles": ["licensor", "producer"],
        "url": "https://gdcs.asu.edu/",
    },
    {
        "name": "Coral Reef Alliance (CORAL)",
        "roles": ["licensor", "producer"],
        "url": "https://coral.org/en/",
    },
    {
        "name": "Planet",
        "roles": ["licensor", "producer"],
        "url": "https://www.planet.com/",
    },
    {
        "name": "Vulcan Inc. (Vulcan)",
        "roles": ["licensor", "producer"],
        "url": "https://vulcan.com/",
    },
]
ACA_START_DATETIME = "2018-01-01T00:00:00Z"
ACA_END_DATETIME = "2021-01-01T00:00:00Z"
ACA_SCI_DOI = "10.5281/zenodo.3833242"
ACA_SCI_CITATION = (
    "Allen Coral Atlas (2020). Imagery, maps and monitoring of the world's "
    "tropical coral reefs. Zenodo. doi:10.5281/zenodo.3833242."
)
ACA_SOURCE_LINKS = [
    {
        "rel": "source",
        "href": "https://storage.googleapis.com/coral-atlas-user-downloads-prod/Global-Dataset-20211006223100.zip",
    },
    {
        "rel": "cite-as",
        "href": "https://doi.org/10.5281/zenodo.3833242",
    },
]
ACA_BANDS = [
    {
        "name": "geomorphic",
        "description": "Classification of geomorphic zonation.",
    },
    {
        "name": "benthic",
        "description": "Classification of dominant benthic composition.",
    },
    {
        "name": "reef_mask",
        "description": (
            "Globally standardised reef extent product integrating reef "
            "classification and bathymetry products."
        ),
    },
]

ACA_PRODUCT_METADATA: dict[str, Any] = {
    "title": ACA_PRODUCT_TITLE,
    "description": ACA_PRODUCT_DESCRIPTION,
    "license": ACA_LICENSE,
    "keywords": ACA_KEYWORDS,
    "providers": ACA_PROVIDERS,
    "start_datetime": ACA_START_DATETIME,
    "end_datetime": ACA_END_DATETIME,
    "gsd": 5.0,
    "doi": ACA_SCI_DOI,
    "citation": ACA_SCI_CITATION,
    "source_links": ACA_SOURCE_LINKS,
    "bands": ACA_BANDS,
}


def aca_product_metadata() -> dict[str, Any]:
    """Return an isolated copy suitable for a dataclass default factory."""

    return deepcopy(ACA_PRODUCT_METADATA)


def validate_product_metadata(metadata: dict[str, Any], band_count: int) -> dict[str, Any]:
    """Validate the metadata fields consumed by the raster and STAC writers."""

    required = {
        "title",
        "description",
        "license",
        "start_datetime",
        "end_datetime",
        "gsd",
        "bands",
    }
    missing = sorted(required - metadata.keys())
    if missing:
        raise ValueError(f"Product metadata is missing required fields: {', '.join(missing)}")

    bands = metadata["bands"]
    if not isinstance(bands, list) or len(bands) != band_count:
        raise ValueError(
            f"Product metadata defines {len(bands) if isinstance(bands, list) else 0} "
            f"bands, but the source tiles contain {band_count}."
        )
    for index, band in enumerate(bands, start=1):
        if not isinstance(band, dict) or not band.get("name"):
            raise ValueError(f"Product metadata band {index} must define a name.")

    return deepcopy(metadata)
