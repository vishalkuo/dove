# Dove
[![PyPI version](https://badge.fury.io/py/droplet-dove.svg)](https://badge.fury.io/py/droplet-dove)

A command line utility to help manage your development server in Digital Ocean

## Why?

Developing on a remote environment provides several advantages over local development such as resource scaling, OS selection, security, and portability. However, as an unemployed student, paying 20-30 dollars a month for a hosted server directly impacts my food budget. Dove helps ease this burden by making it easy to snapshot/rebuild your environment. Given that snapshot pricing is 0.05/GB/month, dove helps reduce the cost of maintaining a remote environment when it's frequently idle.

## How

1.  Generate an API access token on Digital Ocean [here](https://cloud.digitalocean.com/account/api/)
2.  Install dove:

    ```
    pip install droplet_dove
    ```

3.  Initialize dove with `dove init`
4.  Start your droplet with `dove up`
5.  Clean up your droplet and take a snapshot with `dove down`

Additional help: `dove --help`

## How Does It Work?

Dove maintains all of its configuration in `~/.dove_config.json`. You can edit these values manually; however you can use `dove init` for an initial population. Note that all properties under the `droplet` key are passed directly to digital ocean (with exception to the `sshkeys` array), so if addiitonal configuration is required it can be edited there.

### Dove Up

1. Check for a running droplet with the name specified in the dove config, abort if one exists
2. Find the latest snapshot for the prefix provided in dove config or use the default snapshot if none exist
3. Create the droplet with the configuration params
4. Wait for the droplet to start

### Dove Down

1. Get droplet based on name provided in dove config, abort if droplet not found
2. Shutdown droplet and take a snapshot
3. Destroy old snapshots with same prefix
4. Destroy droplet
