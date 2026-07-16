"""Workflow configuration loading and defaults."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

import yaml

from csdr_cog_cruncher.publish import DEFAULT_HTTPS_BASE, DEFAULT_S3_BASE


@dataclass(slots=True)
class WorkflowConfig:
    input_glob: str
    output_dir: Path
    product_id: str
    collection_id: str
    product_metadata: dict[str, Any]
    extent_mode: str = "union"
    global_bounds: tuple[float, float, float, float] = (-180.0, -90.0, 180.0, 90.0)
    compression: str = "ZSTD"
    blocksize: int = 512
    bigtiff: str = "IF_SAFER"
    num_threads: str = "ALL_CPUS"
    overview_resampling: str = "nearest"
    keep_stage: bool = False
    skip_cog: bool = False
    validate_outputs: bool = True
    write_catalog: bool = True
    href_base: str = DEFAULT_HTTPS_BASE
    s3_base: str | None = DEFAULT_S3_BASE
    inventory_filename: str = "inventory.json"
    grid_filename: str = "grid.json"
    vrt_filename: str = "mosaic.vrt"
    stage_filename: str = "mosaic_stage.tif"
    cog_filename: str = "mosaic.tif"
    manifest_filename: str = "build-manifest.json"
    completion_filename: str = "workflow-complete.json"
    item_filename: str = "item.json"

    @property
    def inventory_path(self) -> Path:
        return self.output_dir / self.inventory_filename

    @property
    def grid_path(self) -> Path:
        return self.output_dir / self.grid_filename

    @property
    def vrt_path(self) -> Path:
        return self.output_dir / self.vrt_filename

    @property
    def stage_path(self) -> Path:
        return self.output_dir / self.stage_filename

    @property
    def cog_path(self) -> Path:
        return self.output_dir / self.cog_filename

    @property
    def manifest_path(self) -> Path:
        return self.output_dir / self.manifest_filename

    @property
    def completion_path(self) -> Path:
        return self.output_dir / self.completion_filename

    @property
    def catalog_path(self) -> Path:
        return self.output_dir / "catalog.json"

    @property
    def collection_path(self) -> Path:
        return self.output_dir / self.collection_id / "collection.json"

    @property
    def item_path(self) -> Path:
        return (
            self.output_dir
            / self.collection_id
            / self.product_id
            / f"{self.product_id}.json"
        )

    def serializable_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["output_dir"] = str(self.output_dir)
        return payload


def _load_mapping(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    with path.open("r", encoding="utf-8") as handle:
        if suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(handle)
        else:
            data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration in {path} must be a mapping.")
    return data


def _coerce_path(base_dir: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _coerce_glob(base_dir: Path, value: str) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())


def load_config(
    config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> WorkflowConfig:
    data: dict[str, Any] = {}
    if config_path is not None:
        data.update(_load_mapping(config_path))
        base_dir = config_path.parent.resolve()
    else:
        base_dir = Path.cwd()

    for path_key in ("output_dir",):
        if path_key in data:
            data[path_key] = _coerce_path(base_dir, data[path_key])
    if "input_glob" in data:
        data["input_glob"] = _coerce_glob(base_dir, data["input_glob"])

    if overrides:
        override_data = {key: value for key, value in overrides.items() if value is not None}
        for path_key in ("output_dir",):
            if path_key in override_data:
                override_data[path_key] = _coerce_path(Path.cwd(), override_data[path_key])
        if "input_glob" in override_data:
            override_data["input_glob"] = _coerce_glob(Path.cwd(), override_data["input_glob"])
        data.update(override_data)

    if "global_bounds" in data:
        bounds = tuple(float(value) for value in data["global_bounds"])
        if len(bounds) != 4:
            raise ValueError("global_bounds must contain exactly four numeric values.")
        data["global_bounds"] = bounds

    required = ("input_glob", "output_dir", "product_id", "collection_id", "product_metadata")
    missing = [key for key in required if key not in data]
    if missing:
        source = str(config_path) if config_path is not None else "workflow configuration"
        raise ValueError(f"{source} is missing required fields: {', '.join(missing)}")

    for key in ("product_id", "collection_id", "href_base"):
        if key in data and (not isinstance(data[key], str) or not data[key].strip()):
            raise ValueError(f"{key} must be a non-empty string.")
    if (
        "s3_base" in data
        and data["s3_base"] is not None
        and not isinstance(data["s3_base"], str)
    ):
        raise ValueError("s3_base must be a string or null.")

    return WorkflowConfig(**data)
