import click
import digitalocean
import os
from os import path
import sys
import json
from typing import Dict

HOME_DIR = path.expanduser("~")
DEFAULT_CONFIG = path.join(HOME_DIR, ".dove_config.json")


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    "--config",
    default=DEFAULT_CONFIG,
    help=f"The location of the config file. Defaults to {DEFAULT_CONFIG}",
)
def up(config: str = DEFAULT_CONFIG):
    parsed_config = _load_config(config)
    do_manager = digitalocean.Manager(token=parsed_config["token"])

    # Load snapshots
    snapshot_name = _try_get(parsed_config, "snapshot_name")
    click.echo(f"Searching for snapshot, {snapshot_name}")
    snapshots = do_manager.get_all_snapshots()
    snapshot: digitalocean.Snapshot = next(
        (s for s in snapshots if s.name == snapshot_name), None
    )
    if not snapshot:
        click.secho(f"No snapshot found for {snapshot_name}", fg="red")
        sys.exit(1)

    # Load SSH Keys
    ssh_key_names = set(_try_get(parsed_config, "ssh_keys"))
    ssh_keys = do_manager.get_all_sshkeys()
    ssh_key_set = [key for key in ssh_keys if key.name in ssh_key_names]

    droplet_config = _try_get(parsed_config, "droplet")
    droplet_config["image"] = snapshot.id
    droplet_config["token"] = parsed_config["token"]
    droplet_config["ssh_keys"] = ssh_key_set

    click.echo("Creating droplet...")
    droplet = digitalocean.Droplet(**droplet_config)
    droplet.create()
    print(droplet)


def _load_config(config: str) -> Dict[any, any]:
    if not path.exists(DEFAULT_CONFIG):
        click.secho(f"Config not found at {config}", fg="red")
        sys.exit(1)

    parsed_config = None
    try:
        with open(config, "r") as f:
            data = f.read()
            parsed_config = json.loads(data)
    except json.JSONDecodeError as ex:
        click.secho(f"Could not decode file: {ex}", fg="red")
        sys.exit(1)

    return parsed_config


def _try_get(parsed_config: Dict[any, any], key: any) -> any:
    if key not in parsed_config:
        click.secho(f"Key {key} not found", fg="red")
        sys.exit(1)
    return parsed_config[key]


@cli.command()
def init():
    click.echo("In init")


if __name__ == "__main__":
    cli()
