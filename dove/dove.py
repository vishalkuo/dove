import click
import digitalocean
import os
from os import path
import sys
import json
from typing import Dict
import time

HOME_DIR = path.expanduser("~")
DEFAULT_CONFIG = path.join(HOME_DIR, ".dove_config.json")
DROPLET_POLLS = 3
POLLING_INTERVAL = 5


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

    click.echo(f"Successfully created droplet! Polling to get IP address...")
    for _i in range(DROPLET_POLLS):
        d = do_manager.get_droplet(droplet.id)
        if d.ip_address and d.status == "active":
            click.secho(f"Found IP address:\n\tssh root@{d.ip_address}", fg="green")
            sys.exit(0)
        else:
            time.sleep(POLLING_INTERVAL)

    click.echo(
        "Droplet is still starting up. Please wait or check the digital ocean UI for its status"
    )


@cli.command()
@click.option("--name", "-n", default=None, help="The name of the droplet to check on")
@click.option(
    "--config",
    default=DEFAULT_CONFIG,
    help=f"The location of the config file. Defaults to {DEFAULT_CONFIG}",
)
def status(name: str, config: str = DEFAULT_CONFIG):
    parsed_config = _load_config(config)
    token = _try_get(parsed_config, "token")
    do_manager = digitalocean.Manager(token=token)

    if not name:
        name = _try_get(parsed_config, "droplet")["name"]

    droplet_info = do_manager.get_all_droplets()
    droplet = next((d for d in droplet_info if d.name == name), None)
    if not droplet:
        click.secho(f"Couldn't find droplet for name {name}", fg="red")
        sys.exit(1)

    click.echo(f"status: {droplet.status}")
    click.echo(f"ip address: {droplet.ip_address}")
    click.echo(f"created at: {droplet.created_at}")


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
