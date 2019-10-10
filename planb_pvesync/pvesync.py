from .pvecommand import Command
from .synccommand import SyncFilesystem
from .zfs import LocalFilesystem, RemoteFilesystem


def guestvolume_to_localfs(guestvolume, *, zfs_root):
    fs = (
        LocalFilesystem(zfs_root=zfs_root)
        # .descend(guestvolume.guest.cluster.name)
        .descend(guestvolume.guest.name)
        .descend('{}--{}'.format(
            guestvolume.filestore.name, guestvolume.name)))
    return fs


def guestvolume_to_remotefs(guestvolume, *, zfs_root, run_remote_args):
    fs = (
        RemoteFilesystem(zfs_root=zfs_root, run_remote_args=run_remote_args)
        .descend(guestvolume.name))
    return fs


class SyncGuestVolumes(Command):
    def __init__(self, *, config, guest_name, local_zfs_root):
        super().__init__(config=config, guest_name=guest_name)
        self._local_zfs_root = local_zfs_root

    def run(self):
        guest = self._cluster.get_guest(self._guest_name)
        for guestvolume in sorted(guest.enum_guestvolumes(), key=(
                lambda x: (
                    x.is_enabled, not x.is_boot, x.filestore.name,
                    x.name))):
            if guestvolume.is_enabled and not guestvolume.is_removable:
                self.run_volume(guestvolume)

    def run_volume(self, guestvolume):
        lfs = guestvolume_to_localfs(
            guestvolume, zfs_root=self._local_zfs_root)

        raccess = guestvolume.filestore.remote_access
        if not raccess:
            raise ValueError(
                # Actually.. we don't know how this config is provided, so
                # this exception message is overly specific (and possibly
                # wrong)
                '(probably) missing [storage:{}:{}] in config'.format(
                    guestvolume.guest.cluster.name,
                    guestvolume.filestore.name))
        rfs = guestvolume_to_remotefs(
            guestvolume, zfs_root=guestvolume.filestore.path_or_pool[1],
            run_remote_args=raccess.run_remote_args)

        syncer = SyncFilesystem(srcfs=rfs, dstfs=lfs)
        syncer.run()
