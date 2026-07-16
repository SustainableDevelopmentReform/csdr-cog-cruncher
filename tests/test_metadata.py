from copy import deepcopy
from pathlib import Path

import pytest

from csdr_cog_cruncher.config import load_config
from csdr_cog_cruncher.metadata import validate_product_metadata


METADATA = {
    "title": "Example product",
    "description": "Example description.",
    "license": "CC-BY-4.0",
    "start_datetime": "2019-01-01T00:00:00Z",
    "end_datetime": "2020-12-31T23:59:59Z",
    "gsd": 10.0,
    "bands": [{"name": "data"}],
}


def test_datetime_override_is_validated() -> None:
    metadata = deepcopy(METADATA)
    metadata["datetime"] = "not-a-date"
    with pytest.raises(ValueError, match="valid ISO 8601"):
        validate_product_metadata(metadata, 1)

    metadata["datetime"] = "2022-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="must fall within"):
        validate_product_metadata(metadata, 1)


def test_config_requires_explicit_product_identity(tmp_path: Path) -> None:
    config_path = tmp_path / "incomplete.yaml"
    config_path.write_text("input_glob: '*.tif'\noutput_dir: output\n", encoding="utf-8")

    with pytest.raises(ValueError, match="product_id, collection_id, product_metadata"):
        load_config(config_path)


@pytest.mark.parametrize(
    "profile",
    [
        "configs/aca-workstation.yaml",
        "configs/workflow.example.yaml",
        "configs/seagrass-2019-2020.yaml",
        "configs/seagrass-2023-2024.yaml",
    ],
)
def test_bundled_profiles_declare_valid_product_metadata(profile: str) -> None:
    config = load_config(Path(profile))
    validate_product_metadata(config.product_metadata, len(config.product_metadata["bands"]))
