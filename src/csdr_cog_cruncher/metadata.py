"""Static ACA metadata extracted from the source dataset definition."""

from __future__ import annotations

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
