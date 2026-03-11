"""Command line entry point."""

from __future__ import annotations

from pathlib import Path

import click

from csdr_cog_cruncher.config import load_config
from csdr_cog_cruncher.workflow import run_workflow


@click.command()
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option("--input-glob", type=str, default=None, help="Glob for source tiles.")
@click.option("--output-dir", type=click.Path(path_type=Path), default=None, help="Output directory.")
@click.option(
    "--extent-mode",
    type=click.Choice(["union", "global"], case_sensitive=False),
    default=None,
    help="Output extent policy.",
)
@click.option("--skip-cog", is_flag=True, default=None, help="Keep only the sparse stage GeoTIFF.")
@click.option("--keep-stage", is_flag=True, default=None, help="Preserve the sparse stage GeoTIFF.")
def main(
    config_path: Path | None,
    input_glob: str | None,
    output_dir: Path | None,
    extent_mode: str | None,
    skip_cog: bool | None,
    keep_stage: bool | None,
) -> None:
    """Run the ACA tile merge workflow."""

    config = load_config(
        config_path,
        overrides={
            "input_glob": input_glob,
            "output_dir": output_dir,
            "extent_mode": extent_mode.lower() if extent_mode else None,
            "skip_cog": skip_cog,
            "keep_stage": keep_stage,
        },
    )
    result = run_workflow(config)
    click.echo(f"Inventory: {result.inventory_path}")
    click.echo(f"Grid: {result.grid_path}")
    click.echo(f"VRT: {result.vrt_path}")
    click.echo(f"Data: {result.data_path}")
    click.echo(f"STAC Item: {result.item_path}")
