from .pveapi import PveCluster


class Command:
    def __init__(self, *, config, guest_name=None):
        self._cluster = PveCluster(config)

        if guest_name and guest_name.isdigit():
            guest_name = int(guest_name)  # name or vmid?
        self._guest_name = guest_name


class ListHosts(Command):
    def run(self):
        for host in sorted(self._cluster.enum_hosts(), key=(
                lambda x: x.name)):
            print(host)


class ListGuests(Command):
    def run(self):
        for guest in sorted(self._cluster.enum_guests(), key=(
                lambda x: (x.is_running, x.type, x.name))):
            if self._guest_name:
                if not guest.match(self._guest_name):
                    continue
            elif not guest.is_running:
                continue

            print(guest)
            for guestvolume in sorted(guest.enum_guestvolumes(), key=(
                    lambda x: (
                        x.is_enabled, not x.is_boot, x.filestore.name,
                        x.name))):
                if guestvolume.is_enabled and not guestvolume.is_removable:
                    print(
                        ' ', guestvolume, guestvolume.filestore.remote_access)


class ListFilestores(Command):
    def run(self):
        for filestore in sorted(self._cluster.enum_filestores(), key=(
                lambda x: (x.is_enabled, x.type, x.name))):
            if filestore.is_enabled:
                print(filestore, filestore.remote_access)
