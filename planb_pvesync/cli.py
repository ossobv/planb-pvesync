from argparse import ArgumentParser, ArgumentError, ArgumentTypeError
from collections import OrderedDict
from functools import wraps

from . import pvecommand, pvesync
from .config import ConfigFile


PVE_COMMANDS = OrderedDict([
    ('list-pve-hosts', pvecommand.ListHosts),
    ('list-pve-guests', pvecommand.ListGuests),
    ('list-pve-filestores', pvecommand.ListFilestores),
    ('sync-pve-guest', pvesync.SyncGuestVolumes),
])
SYNC_COMMANDS = OrderedDict([
])
COMMANDS = OrderedDict()
COMMANDS.update(PVE_COMMANDS)
COMMANDS.update(SYNC_COMMANDS)


def argparse_type(fun):
    @wraps(fun)
    def _inner(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except ArgumentTypeError:
            raise
        except Exception as e:
            raise ArgumentTypeError(str(e)) from e
    return _inner


class PlanbProxSync:
    def main(self):
        assert not hasattr(self, '_args')
        parser = ArgumentParser(
            description=(
                'planb-proxsync connects PlanB Backups to the '
                'Proxmox Virtual Environment.\n\n'
                'It can list Proxmox VMs and filesystems and it '
                'can export those to PlanB.'),
            epilog=(
                'Configuration should be placed in ~/.proxmoxrc or in '
                'a file supplied by -f. Sections therein are named '
                '[pve:clustername] with key api=https://USER:PASS@HOST'))
        parser.add_argument(
            '--config', '-f', action='store', metavar='FILENAME',
            type=argparse_type(ConfigFile), default='~/.proxmoxrc')
        parser.add_argument(
            'command', choices=COMMANDS.keys())
        parser.add_argument(
            '--pve-cluster', '-p', action='store', metavar='CLUSTERNAME')
        parser.add_argument(
            '--pve-guest', '-g', action='store', metavar='GUESTNAME')
        parser.add_argument(
            '--sync-zfs-root', action='store', metavar='DEST_FILESYSTEM')
        self._parser = parser
        self._args = parser.parse_args()
        self._config = self._args.config
        try:
            self._try_command(self._args.command)
        except ArgumentError as e:
            self._parser.error(str(e))

    def _make_argument_error(self, dest, message):
        actions = [i for i in self._parser._actions if i.dest == dest]
        assert len(actions) == 1, (
            dest, actions, [i.dest for i in self._parser._actions])
        return ArgumentError(actions[0], message)

    def _try_command(self, command):
        if command in PVE_COMMANDS:
            run_class = PVE_COMMANDS[command]

            # Get pve-cluster
            if not self._args.pve_cluster:
                raise self._make_argument_error(
                    'command',
                    '{} requires --pve-cluster option'.format(command))
            try:
                pve_config = self._config.get_pve_config(
                    self._args.pve_cluster)
            except Exception as e:
                raise self._make_argument_error('pve_cluster', str(e)) from e

            # Run command
            if command == 'sync-pve-guest':
                if not self._args.sync_zfs_root:
                    raise self._make_argument_error(
                        'command',
                        '{} requires --sync-zfs-root option'.format(command))
                run_command = run_class(
                    config=pve_config, guest_name=self._args.pve_guest,
                    local_zfs_root=self._args.sync_zfs_root)
            else:
                run_command = run_class(
                    config=pve_config, guest_name=self._args.pve_guest)
            run_command.run()

        else:
            raise self._make_argument_error(
                'command', 'unknown command {!r}'.format(command))
