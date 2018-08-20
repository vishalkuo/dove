import unittest
from click.testing import CliRunner
from unittest.mock import patch, mock_open, MagicMock, call
import json
from ..dove import cli, DEFAULT_CONFIG

patch_base = "dove.dove"
do_patch = ".".join([patch_base, "digitalocean"])
time_patch = ".".join([patch_base, "time"])
datetime_patch = ".".join([patch_base, "datetime"])


@patch(time_patch)
@patch(do_patch)
class TestDove(unittest.TestCase):
    def setUp(self):
        self.config = {
            "token": "t_token",
            "droplet": {
                "region": "nyc1",
                "size": "s-2vcpu-4gb",
                "image": "ubuntu-16-04-x64",
                "backups": False,
                "ipv6": False,
                "user_data": None,
                "private_networking": None,
                "volumes": None,
                "name": "t_name",
            },
            "ssh_keys": ["Macbook", "Windows"],
            "snapshot_prefix": "t_prefix",
        }
        self.droplet_config = self.config["droplet"]
        self.raw_config = json.dumps(self.config, indent=2)
        self.manager = MagicMock()
        self.droplet = MagicMock()
        self.droplet.name = self.droplet_config["name"]
        self.droplet.ip_address = "1.1.1.1"
        self.droplet.status = "active"
        self.droplet.created_at = "foo"
        self.snapshot = MagicMock()
        self.snapshot.name = f"{self.config['snapshot_prefix']} - foo"
        self.snapshot.id = 100
        self.ssh_keys = []
        for key in self.config["ssh_keys"]:
            ssh_key = MagicMock()
            ssh_key.name = key
            self.ssh_keys.append(ssh_key)

    def test_init(self, do, time):
        cli_input = "\n".join(
            [
                self.config["token"],
                self.droplet_config["region"],
                self.droplet_config["size"],
                self.droplet_config["image"],
                self.droplet_config["name"],
                "Macbook,Windows",
                self.config["snapshot_prefix"],
            ]
        )
        m = mock_open()
        with patch("builtins.open", m, create=True):
            CliRunner().invoke(cli, ["init"], input=cli_input)
            self.assertEqual(call(DEFAULT_CONFIG, "w"), m.mock_calls[0])
            self.assertEqual(call().write(self.raw_config), m.mock_calls[2])

    def test_up_with_malformed_config(self, do, time):
        with patch("builtins.open", mock_open(read_data="foo")):
            result = CliRunner().invoke(cli, ["up"])
            self.assertTrue(result.output.startswith("Could not decode file"))
            self.assertEqual(1, result.exit_code)

    def test_up_with_running_server(self, do, time):
        do.Manager.return_value = self.manager
        self.manager.get_all_droplets.return_value = [self.droplet]

        with patch("builtins.open", mock_open(read_data=self.raw_config)):
            result = CliRunner().invoke(cli, ["up"])
            self.assertEqual(1, result.exit_code)

    def test_up_with_existing_snapshot(self, do, time):
        do.Manager.return_value = self.manager
        do.Droplet.return_value = self.droplet
        self.manager.get_all_droplets.return_value = []
        self.manager.get_all_snapshots.return_value = [self.snapshot]
        self.manager.get_all_sshkeys.return_value = self.ssh_keys

        with patch("builtins.open", mock_open(read_data=self.raw_config)):
            result = CliRunner().invoke(cli, ["up"])
            do.Droplet.assert_called_with(
                token=self.config["token"],
                region=self.droplet_config["region"],
                size=self.droplet_config["size"],
                image=self.snapshot.id,
                backups=False,
                ipv6=False,
                user_data=None,
                private_networking=None,
                volumes=None,
                name=self.droplet_config["name"],
                ssh_keys=self.ssh_keys,
            )
            self.assertEqual(0, result.exit_code)
            time.sleep.assert_not_called()

    def test_up_with_missing_snapshot(self, do, time):
        do.Manager.return_value = self.manager
        do.Droplet.return_value = self.droplet
        self.manager.get_all_droplets.return_value = []
        self.manager.get_all_snapshots.return_value = []
        self.manager.get_all_sshkeys.return_value = self.ssh_keys

        with patch("builtins.open", mock_open(read_data=self.raw_config)):
            result = CliRunner().invoke(cli, ["up"], input="y\n")
            do.Droplet.assert_called_with(
                token=self.config["token"],
                region=self.droplet_config["region"],
                size=self.droplet_config["size"],
                image=self.droplet_config["image"],
                backups=False,
                ipv6=False,
                user_data=None,
                private_networking=None,
                volumes=None,
                name=self.droplet_config["name"],
                ssh_keys=self.ssh_keys,
            )
            self.assertEqual(0, result.exit_code)
            time.sleep.assert_not_called()

    def test_status_if_missing(self, do, time):
        do.Manager.return_value = self.manager
        self.manager.get_all_droplets.return_value = []
        with patch("builtins.open", mock_open(read_data=self.raw_config)):
            result = CliRunner().invoke(cli, ["status"])
            self.assertEqual(1, result.exit_code)

    def test_status_if_exists(self, do, time):
        do.Manager.return_value = self.manager
        self.manager.get_all_droplets.return_value = [self.droplet]
        with patch("builtins.open", mock_open(read_data=self.raw_config)):
            result = CliRunner().invoke(cli, ["status"])
            self.assertEqual(
                "status: active\nip_address: 1.1.1.1\ncreated_at: foo\n", result.output
            )
            self.assertEqual(0, result.exit_code)

    def test_down_if_no_droplet(self, do, time):
        do.Manager.return_value = self.manager
        self.manager.get_all_droplets.return_value = []
        with patch("builtins.open", mock_open(read_data=self.raw_config)):
            result = CliRunner().invoke(cli, ["down"])
            self.assertEqual(1, result.exit_code)

    @patch(datetime_patch)
    def test_down_if_droplet_and_finished_snapshot(self, datetime, do, time):
        suffix = "bar"
        do.Manager.return_value = self.manager
        self.manager.get_all_droplets.return_value = [self.droplet]
        datetime.now.return_value = suffix
        do_result = MagicMock()
        do_result.status = "completed"
        self.droplet.take_snapshot.return_value = do_result

        snapshot_name = f"{self.config['snapshot_prefix']} - {suffix}"
        new_snapshot = MagicMock()
        new_snapshot.name = snapshot_name

        self.manager.get_all_snapshots.return_value = [self.snapshot, new_snapshot]

        with patch("builtins.open", mock_open(read_data=self.raw_config)):
            result = CliRunner().invoke(cli, ["down"])
            self.droplet.take_snapshot.assert_called_with(
                snapshot_name, return_dict=False, power_off=True
            )
            do_result.load.assert_called_with()
            self.snapshot.destroy.assert_called_with()
            self.droplet.destroy.assert_called_with()
            self.assertEqual(0, result.exit_code)

    @patch(datetime_patch)
    def test_down_if_droplet_and_unfinished_snapshot(self, datetime, do, time):
        suffix = "foo"
        do.Manager.return_value = self.manager
        self.manager.get_all_droplets.return_value = [self.droplet]
        datetime.now.return_value = suffix
        do_result = MagicMock()
        do_result.status = "incomplete"
        self.droplet.take_snapshot.return_value = do_result

        with patch("builtins.open", mock_open(read_data=self.raw_config)):
            result = CliRunner().invoke(cli, ["down"])
            self.droplet.take_snapshot.assert_called_with(
                f"{self.config['snapshot_prefix']} - {suffix}",
                return_dict=False,
                power_off=True,
            )
            do_result.load.assert_called_with()
            self.assertEqual(1, result.exit_code)
