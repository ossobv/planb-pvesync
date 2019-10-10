from datetime import datetime
from subprocess import check_call

from .zfs import ZfsError


class NoCommonSnapshots(Exception):
    def __init__(self, left, left_snaps, right, right_snaps):
        self.left = left
        self.left_snaps = left_snaps
        self.right = right
        self.right_snaps = right_snaps

    def __str__(self):
        return (
            'No common snapshots found between {left!r} and {right!r}:\n'
            '- {{{left_snaps}}}\nvs\n- {{{right_snaps}}}\n').format(
                left=self.left, right=self.right,
                left_snaps='\n- '.join(sorted(self.left_snaps)),
                right_snaps='\n- '.join(sorted(self.right_snaps)))


class SyncFilesystem:
    def __init__(self, *, srcfs, dstfs):
        self._srcfs = srcfs
        self._dstfs = dstfs

    def run(self):
        try:
            newest_common, source_snaps, dest_snaps = self.get_snapshots()
        except NoCommonSnapshots as e:
            if e.right_snaps:
                raise
            self.sync_initial(e.left_snaps)
        else:
            self.sync_increment(source_snaps, newest_common)

    def sync_initial(self, source_snapshots):
        if source_snapshots:
            snapshot = source_snapshots[-1]  # take newest
        else:
            snapshot = self.create_source_snapshot()  # create new

        self._dstfs.ensure_parent_exists()

        # Assemble send/recv commands
        expected_size = self._srcfs.send_snapshot_size(snapshot)
        sendcmd = self._srcfs.send_snapshot_command(snapshot)
        recvcmd = self._dstfs.recv_command(
            pre_pipe='pv -ptebar -B512M -w72 -s{}'.format(expected_size))
        shcmd = ['/bin/sh', '-c', '{} | {}'.format(
            sendcmd.as_shell(), recvcmd.as_shell())]
        print('EXEC1', shcmd)
        check_call(shcmd)
        # FIXME: todo: check snapshot for success..?

    def sync_increment(self, source_snapshots, prev_snapshot):
        assert source_snapshots
        if source_snapshots[-1] != prev_snapshot:
            snapshot = source_snapshots[-1]  # take newest
        else:
            snapshot = self.create_source_snapshot()  # create new

        expected_size = self._srcfs.send_snapshot_size(
            snapshot, prev_snapshot_name=prev_snapshot)
        sendcmd = self._srcfs.send_snapshot_command(
            snapshot, prev_snapshot_name=prev_snapshot)
        recvcmd = self._dstfs.recv_command(
            pre_pipe='pv -ptebar -B512M -w72 -s{}'.format(expected_size))
        shcmd = ['/bin/sh', '-c', '{} | {}'.format(
            sendcmd.as_shell(), recvcmd.as_shell())]
        print('EXEC2', shcmd)
        check_call(shcmd)
        # FIXME: todo: check snapshot for success..?

    def create_source_snapshot(self):
        now = datetime.now()
        snapshot_name = 'daily-{}'.format(now.strftime('%Y%m%d%H%M'))
        self._srcfs.make_snapshot(snapshot_name)
        return snapshot_name

    def get_snapshots(self):
        # FIXME: make sane function name and return signature
        # Get remote and local snapshots.
        source_snaps = self._srcfs.get_snapshots_by_date()
        try:
            dest_snaps = self._dstfs.get_snapshots_by_date()
        except ZfsError:
            dest_snaps = []  # nothing found?

        # Find a common snapshot, oldest first.
        common_snaps = set(source_snaps) & set(dest_snaps)
        for snapshot in reversed(source_snaps):
            if snapshot in common_snaps:
                return (snapshot, source_snaps, dest_snaps)

        raise NoCommonSnapshots(
            left=self._srcfs, left_snaps=source_snaps,
            right=self._dstfs, right_snaps=dest_snaps)
