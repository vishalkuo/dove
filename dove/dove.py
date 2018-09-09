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
DROPLET_POLLS = 10
POLLING_INTERVAL = 5
SNAPSHOT_POLLS = 360
SNAPSHOT_INTERVAL = 10


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    "--config",
    default=DEFAULT_CONFIG,
    help=f"The location of the config file. Defaults to {DEFAULT_CONFIG}",
)
def init(config: str):
    token = click.prompt("Enter your access token", hide_input=True, type=str)
    region = click.prompt(
        "Enter the region you'd like to use for your droplet", type=str, default="nyc1"
    )
    size = click.prompt(
        "Enter the droplet size you'd like to use", type=str, default="s-2vcpu-4gb"
    )
    image = click.prompt(
        "Enter the image you'd like to use", type=str, default="ubuntu-16-04-x64"
    )
    name = click.prompt("Enter the name you'd like to give your droplet", type=str)
    ssh_raw = click.prompt(
        "Enter the ssh keys, comma separated, that will have access to your droplet",
        type=str,
    )
    snapshot_prefix = click.prompt(
        "Enter the snapshot prefix you'd like to use (must be unique)"
    )

    ssh_keys = [s.strip() for s in ssh_raw.split(",")]

    dove_config = {
        "token": token,
        "droplet": {
            "region": region,
            "size": size,
            "image": image,
            "backups": False,
            "ipv6": False,
            "user_data": None,
            "private_networking": None,
            "volumes": None,
            "name": name,
        },
        "ssh_keys": ssh_keys,
        "snapshot_prefix": snapshot_prefix,
    }

    with open(config, "w") as f:
        data = json.dumps(dove_config, indent=2)
        f.write(data)

    click.echo(f"Wrote configuration to {config}")


@cli.command()
@click.option(
    "--config",
    default=DEFAULT_CONFIG,
    help=f"The location of the config file. Defaults to {DEFAULT_CONFIG}",
)
def up(config: str):
    parsed_config = _load_config(config)
    manager = digitalocean.Manager(token=parsed_config["token"])

    # Check for already running server
    droplet_config = _try_get(parsed_config, "droplet")
    click.echo("Checking for pre-existing droplet...")
    droplet_name = droplet_config["name"]
    existing = _get_droplet_by_name(droplet_name, manager, fail_if_missing=False)
    if existing:
        click.secho(f"Droplet with name {droplet_name} already exists, aborting")
        sys.exit(1)

    # Load snapshots
    snapshot_prefix = _try_get(parsed_config, "snapshot_prefix")
    click.echo(f"Searching for snapshot with prefix: {snapshot_prefix}")
    snapshots = _get_snapshots_with_prefix(snapshot_prefix, manager)

    image = droplet_config["image"]
    if not snapshots:
        click.confirm(
            f"No snapshot found with prefix: {snapshot_prefix}, would you like to use the default: {image}?",
            abort=True,
        )
    else:
        # Take the latest snapshot
        snapshot = sorted(snapshots)[-1]
        image = snapshot.id

    # Load SSH Keys
    ssh_key_names = set(_try_get(parsed_config, "ssh_keys"))
    ssh_keys = manager.get_all_sshkeys()
    ssh_key_set = [key for key in ssh_keys if key.name in ssh_key_names]

    # Make request
    droplet_config["image"] = image
    droplet_config["token"] = parsed_config["token"]
    droplet_config["ssh_keys"] = ssh_key_set

    click.echo("Creating droplet...")
    droplet = digitalocean.Droplet(**droplet_config)
    droplet.create()

    click.echo(f"Successfully created droplet! Polling until active...")
    for _i in range(DROPLET_POLLS):
        droplet.load()
        if droplet.ip_address and droplet.status == "active":
            click.secho(
                f"Droplet is active, access at:\n\tssh root@{droplet.ip_address}",
                fg="green",
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
    manager = digitalocean.Manager(token=token)

    name = name or _try_get(parsed_config, "droplet")["name"]

    droplet = _get_droplet_by_name(name, manager)

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

    click.echo("Shutting down droplet and taking snapshot...")
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
    name: str, manager: digitalocean.Manager, fail_if_missing=True
) -> digitalocean.Droplet:
    droplets = manager.get_all_droplets()
    droplet: digitalocean.Droplet = next((d for d in droplets if d.name == name), None)
    if not droplet and fail_if_missing:
        click.secho(f"No droplet found for name: {name}", fg="red")
        sys.exit(1)
    return droplet


def _load_config(config: str) -> Dict[any, any]:
    if not path.exists(config):
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
