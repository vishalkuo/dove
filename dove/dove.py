import click
import digitalocean
import os
from os import path
import sys
import json
from typing import Dict, List
import time
from datetime import datetime

HOME_DIR = path.expanduser("~")
DEFAULT_CONFIG = path.join(HOME_DIR, ".dove_config.json")
DROPLET_POLLS = 3
POLLING_INTERVAL = 5
SNAPSHOT_POLLS = 360
SNAPSHOT_INTERVAL = 10


@click.group()
def cli():
    pass


@cli.command()
def init():
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
    snapshot_prefix = _try_get(parsed_config, "snapshot_prefix")
    click.echo(f"Searching for snapshot with prefix: {snapshot_prefix}")
    snapshots = do_manager.get_all_snapshots()
    snapshot: digitalocean.Snapshot = next(
        (s for s in snapshots if s.name.startswith(snapshot_prefix)), None
    )
    if not snapshot:
        click.secho(f"No snapshot found with prefix: {snapshot_prefix}", fg="red")
        sys.exit(1)

    # Load SSH Keys
    ssh_key_names = set(_try_get(parsed_config, "ssh_keys"))
    ssh_keys = do_manager.get_all_sshkeys()
    ssh_key_set = [key for key in ssh_keys if key.name in ssh_key_names]

    # Make request
    droplet_config = _try_get(parsed_config, "droplet")
    droplet_config["image"] = snapshot.id
    droplet_config["token"] = parsed_config["token"]
    droplet_config["ssh_keys"] = ssh_key_set

    click.echo("Creating droplet...")
    droplet = digitalocean.Droplet(**droplet_config)
    droplet.create()

    click.echo(f"Successfully created droplet! Polling to get IP address...")
    for _i in range(DROPLET_POLLS):
        droplet.load()
        if droplet.ip_address and droplet.status == "active":
            click.secho(
                f"Found IP address:\n\tssh root@{droplet.ip_address}", fg="green"
            )
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

    for key in ["status", "ip_address", "created_at"]:
        click.echo(f"{key}: {getattr(droplet, key)}")


@cli.command()
@click.option(
    "--config",
    default=DEFAULT_CONFIG,
    help=f"The location of the config file. Defaults to {DEFAULT_CONFIG}",
)
def down(config: str = DEFAULT_CONFIG):
    parsed_config = _load_config(config)
    token = _try_get(parsed_config, "token")
    manager = digitalocean.Manager(token=token)

    droplet_name = _try_get(parsed_config, "droplet")["name"]
    droplet = _get_droplet_by_name(droplet_name, manager)
    snapshot_prefix = _try_get(parsed_config, "snapshot_prefix")
    snapshot_name = f"{snapshot_prefix} - {str(datetime.now())}"

    click.echo("Shutting down and starting snapshot...")
    result = droplet.take_snapshot(snapshot_name, return_dict=False, power_off=True)

    click.echo("Waiting for snapshot to complete. This can take up to an hour...")
    for _i in range(SNAPSHOT_POLLS):
        try:
            result.load()
        except digitalocean.baseapi.DataReadError as ex:
            click.secho(f"Warning, error during polling: {ex}", fg="yellow")
        if result.status == "completed":
            break
        else:
            time.sleep(SNAPSHOT_INTERVAL)

    if result.status != "completed":
        # TODO: check for in progress snapshots
        click.secho(
            "Snapshot hasn't finished in a reasonable interval, please run manual cleanup",
            fg="red",
        )
        sys.exit(1)

    prefix = _try_get(parsed_config, "snapshot_prefix")
    all_snapshots = _get_snapshots_with_prefix(prefix, manager)
    to_delete = filter(lambda s: s.name != snapshot_name, all_snapshots)

    click.echo("Deleting old snapshots...")

    for snapshot in to_delete:
        snapshot.destroy()

    click.echo("Destroying droplet...")
    droplet.destroy()


def _get_snapshots_with_prefix(
    prefix: str, manager: digitalocean.Manager
) -> List[digitalocean.Snapshot]:
    all_snapshots = manager.get_all_snapshots()
    return set(filter(lambda s: s.name.startswith(prefix), all_snapshots))


def _get_droplet_by_name(
    name: str, manager: digitalocean.Manager
) -> digitalocean.Droplet:
    droplets = manager.get_all_droplets()
    droplet: digitalocean.Droplet = next((d for d in droplets if d.name == name), None)
    if not droplet:
        click.secho(f"No droplet found for name: {name}", fg="red")
        sys.exit(1)
    return droplet


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


if __name__ == "__main__":
    cli()
