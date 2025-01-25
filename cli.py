import logging
import os
from pathlib import Path

import json5
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from typing_extensions import Annotated

from firefly_importer import FireflyImporter
from transaction import Config

__version__ = "1.0"

cli = typer.Typer(add_completion=False, no_args_is_help=True)


@cli.callback()
def common_options(
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True)] = 0,
    quiet: bool = typer.Option(False, "--quiet", "-q"),
    version: bool = typer.Option(False, "--version"),
):
    """Common options:"""

    if version:
        print(__version__)
        raise SystemExit

    log_level = logging.WARNING - verbose * 10
    log_level = logging.CRITICAL if quiet else log_level
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[RichHandler(markup=False, console=Console(width=180))],
    )

    load_dotenv()


@cli.command()
def load_csv(
    csv_file: str,
    config_file: Path = typer.Option(..., help="Input path to a file or directory"),
):
    base_url = os.getenv("FIREFLY_URL")
    access_token = os.getenv("ACCESS_TOKEN")

    if base_url is None:
        raise ValueError("FIREFLY_URL environment variable is not set")

    if access_token is None:
        raise ValueError("ACCESS_TOKEN environment variable is not set")

    importer = FireflyImporter(base_url=base_url, access_token=access_token)

    csv_config = Config(**json5.load(open(config_file, "r")))

    importer.import_from_csv(
        csv_file=csv_file,
        csv_config=csv_config,
    )


if __name__ == "__main__":
    cli()
