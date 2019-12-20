from shlex import quote as shell_quote
from subprocess import CalledProcessError, check_output


class ZfsError(CalledProcessError):
    pass


class ZfsCommand:
    def __init__(self, args, pre_pipe=None, post_pipe=None):
        self.args = args
        self.pre_pipe = pre_pipe
        self.post_pipe = post_pipe

    def exec(self):
        assert self.pre_pipe is None
        assert self.post_pipe is None
        try:
            ret = check_output(self.args).decode('utf-8').strip()
        except CalledProcessError as e:
            raise ZfsError(*e.args) from e
        if not ret:
            return None
        return ret

    def as_shell(self):
        cmd = ' '.join(shell_quote(i) for i in self.args)
        if self.pre_pipe:
            cmd = '{} | {}'.format(self.pre_pipe, cmd)
        if self.post_pipe:
            cmd = '{} | {}'.format(cmd, self.post_pipe)
        return cmd


class _SystemCalls:
    def zfs_command(self, *args):
        raise NotImplementedError()

    def zfs_exec(self, *args):
        cmd = self.zfs_command(*args)
        return cmd.exec()


class _FilesystemBase(_SystemCalls):
    def __init__(self, *, zfs_root, **kwargs):
        super().__init__(**kwargs)

        assert not zfs_root.startswith('/'), zfs_root
        assert not zfs_root.endswith('/'), zfs_root
        self._fs_name = zfs_root  # 'tank', or 'tank/enc'

    def __repr__(self):
        return '<zfs:{}>'.format(self._fs_name)

    def descend(self, child_name):
        assert not child_name.startswith('/'), child_name
        assert not child_name.endswith('/'), child_name
        self._fs_name = '{}/{}'.format(self._fs_name, child_name)
        return self

    def ensure_parent_exists(self):
        assert '/' in self._fs_name, self._fs_name
        self.zfs_exec('zfs', 'create', '-p', self._fs_name.rsplit('/', 1)[0])

    def make_snapshot(self, snapshot_name):
        # FIXME: validate snapshot_name for illegal chars..?
        self.zfs_exec(
            'zfs', 'snapshot', '{}@{}'.format(self._fs_name, snapshot_name))

    def get_snapshots_by_date(self):
        ret = self.zfs_exec(
            'zfs', 'list', '-r', '-Honame', '-screation', '-tsnapshot',
            self._fs_name)
        if not ret:
            return []

        # Split by LF and remove fs_name@ prefix.
        snaps = ret.split('\n')
        snap_prefix = '{}@'.format(self._fs_name)
        for snap in snaps:
            assert snap.startswith(snap_prefix), snaps
        snaps = [snap[len(snap_prefix):] for snap in snaps]
        return snaps

    def send_snapshot_size(self, snapshot_name, prev_snapshot_name=None):
        if prev_snapshot_name:
            ret = self.zfs_exec(
                'zfs', 'send', '-Pnv', '-i',
                '{}@{}'.format(self._fs_name, prev_snapshot_name),
                '{}@{}'.format(self._fs_name, snapshot_name))
        else:
            ret = self.zfs_exec(
                'zfs', 'send', '-Pnv',
                '{}@{}'.format(self._fs_name, snapshot_name))
        try:
            size_line = [
                i for i in ret.split('\n')
                if i.startswith('size') and i[4:5] in ' \t']
            size = int(size_line[0].split()[1])
        except Exception:
            raise ValueError('expected "size<TAB><SIZE>"', ret)
        return size

    def send_snapshot_command(self, snapshot_name, prev_snapshot_name=None):
        # FIXME: validate snapshot_name for illegal chars..?
        if prev_snapshot_name:
            return self.zfs_command(
                'zfs', 'send', '-i',
                '{}@{}'.format(self._fs_name, prev_snapshot_name),
                '{}@{}'.format(self._fs_name, snapshot_name),
                post_pipe='qlzip1')
        return self.zfs_command(
            'zfs', 'send', '{}@{}'.format(self._fs_name, snapshot_name),
            post_pipe='qlzip1')

    def recv_command(self, pre_pipe=None):
        default_pre_pipe = 'qlzcat1'
        if pre_pipe:
            pre_pipe = '{} | {}'.format(default_pre_pipe, pre_pipe)
        else:
            pre_pipe = default_pre_pipe

        # FIXME: add optional '-F' for --force-overwrite to fix problems with
        # source and destination being unequal
        return self.zfs_command(
            'zfs', 'recv', self._fs_name, pre_pipe=pre_pipe)


class LocalFilesystem(_FilesystemBase):
    def zfs_command(self, *args, pre_pipe=None, post_pipe=None):
        assert args[0] == 'zfs', 'Only supported zfs arg for now'
        args = ('sudo', 'zfs') + args[1:]
        return ZfsCommand(args, pre_pipe=pre_pipe, post_pipe=post_pipe)


class RemoteFilesystem(_FilesystemBase):
    def __init__(self, *, run_remote_args, **kwargs):
        super().__init__(**kwargs)
        self._run_remote_args = tuple(run_remote_args)  # ('ssh', 'user@host')

    def zfs_command(self, *args, pre_pipe=None, post_pipe=None):
        assert args[0] == 'zfs', 'Only supported zfs arg for now'
        remote_args = ('sudo', 'zfs') + tuple(args[1:])
        # Make the call into a single argument: "'zfs' 'list' '...'"
        remote_arg = ' '.join(shell_quote(i) for i in remote_args)
        # Put pre_pipe and post_pipe inside the (remote) shell command.
        if pre_pipe:
            remote_arg = '{} | {}'.format(pre_pipe, remote_arg)
        if post_pipe:
            remote_arg = '{} | {}'.format(remote_arg, post_pipe)
        # Prepend remote args: ('ssh', 'user@host', "'zfs' 'list' '...'")
        args = self._run_remote_args + (remote_arg,)
        return ZfsCommand(args, pre_pipe=None, post_pipe=None)
