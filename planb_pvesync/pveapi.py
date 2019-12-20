import logging

from proxmoxer import ProxmoxAPI

log = logging.getLogger(__name__)


class PveCluster:
    """
    Wrapper around ProxmoxAPI.
    """
    def __init__(self, config):
        self._config = config
        self._name = config.host
        self._api = ProxmoxAPI(
            host=config.host, port=config.port, user=config.user,
            password=config.password, verify_ssl=config.verify_ssl)

    @property
    def name(self):
        return self._name

    def enum_hosts(self):
        for node in (
                # self._api.cluster.resources.get(type='node')):
                self._api.nodes.get()):
            yield PveHost(self, **node)

    def enum_guests(self):
        for vm in self._api.cluster.resources.get(type='vm'):
            yield PveGuest(self, **vm)

    def enum_filestores(self):
        for storage in (
                # self._api.cluster.resources.get(type='storage')):
                self._api.storage.get()):
            filestore = PveFilestore(self, **storage)
            try:
                access = self._config.get_filestore_remote_access(
                    filestore.name)
            except KeyError:
                pass
            else:
                filestore.set_remote_access(access)
            yield filestore

    def get_guest(self, name):
        if not hasattr(self, '_get_filestore'):
            # Add by name.
            self._get_guest = dict(
                (i.name, i) for i in self.enum_guests())

            # Also add by VMID.
            for value in list(self._get_guest.values()):
                if value.vmid in self._get_guest.values():
                    raise ValueError(
                        'did you name a VM with only a number {}?'.format(
                            value.vmid))
                self._get_guest[value.vmid] = value

        return self._get_guest[name]

    def get_filestore(self, name):
        if not hasattr(self, '_get_filestore'):
            self._get_filestore = dict(
                (i.name, i) for i in self.enum_filestores())

            # Also add the "empty"/NULL store; make it disabled.
            self._get_filestore[None] = PveFilestore(
                self, type='void', storage=None, disable=1)

        return self._get_filestore[name]


class PveHost:
    """
    {'maxcpu': 20, 'id': 'node/mc15-2-pve', 'node': 'mc15-2-pve',
     'disk': 1236271104, 'level': '', 'type': 'node',
     'maxdisk': 903810514944, 'maxmem': 135086346240,
     'uptime': 22902257, 'mem': 107509829632, 'cpu': 0.129179430411847}
    """
    def __init__(self, cluster, type, id, node, **kwargs):
        assert type == 'node', (id, type, node)
        assert '{}/{}'.format(type, node) == id, (id, type, node)
        self.cluster = cluster
        self.type = type
        self.name = node

    def __repr__(self):
        """
        MYCLUSTER/node/mc15-1-pve
        """
        return '{cluster.name}/{o.type}/{o.name}'.format(
            cluster=self.cluster, o=self)


class PveFilestore:
    """
    {'storage': 'mc15-1-pve-local-ssd-r10', 'digest':
     '7e97802a7a0fd834ee6c8225ef97be2391013dff', 'content': 'rootdir,images',
     'sparse': 1, 'pool': 'data', 'type': 'zfspool', 'nodes': 'mc15-1-pve'}
    """
    def __init__(self, cluster, type, storage, **kwargs):
        self.cluster = cluster
        self.type = type
        self.name = storage
        self.is_enabled = (not int(kwargs.pop('disable', 0)))
        self.path_or_pool = (
            kwargs.pop('path', None), kwargs.pop('pool', None))
        self.remote_access = None

    def set_remote_access(self, access):
        assert not self.remote_access
        self.remote_access = access

    def __repr__(self):
        return (
            '{cluster.name}/{o.type}/{o.name}'
            '({on};{o.path_or_pool})').format(
                cluster=self.cluster, o=self,
                on=('on' if self.is_enabled else 'OFF'))


class PveGuest:
    def __init__(self, cluster, type, name, id, vmid, node, status, **kwargs):
        """
        {'netout': 269977144343, 'uptime': 5447767, 'maxmem': 8589934592,
         'disk': 0, 'node': 'mc15-1-pve', 'id': 'qemu/152', 'maxcpu': 2,
         'pool': 'acme-tech', 'maxdisk': 53687091200, 'type': 'qemu',
         'vmid': 152, 'status': 'running', 'template': 0,
         'netin': 287520743388, 'mem': 7865589541, 'cpu': 0.193879848753246,
         'name': 'acme-tech-web02-2019',
         'diskwrite': 756173405184, 'diskread': 674792711168}
        """
        assert type in ('lxc', 'qemu'), (vmid, type)
        assert isinstance(vmid, int)
        assert '{}/{}'.format(type, vmid) == id, (id, type, vmid)
        self.cluster = cluster
        self.type = type
        self.name = name
        self.vmid = vmid
        self.node = node
        if status == 'running':
            self.is_running = True
            self.is_stopped = False
        elif status == 'stopped':
            self.is_running = False
            self.is_stopped = True
        else:
            raise NotImplementedError((vmid, status))

    def match(self, name_or_vmid):
        if isinstance(name_or_vmid, int):
            return (self.vmid == name_or_vmid)
        return (self.name == name_or_vmid)

    def enum_guestvolumes(self):
        """
        {'memory': 4096, 'arch': 'amd64',
         'rootfs': 'mc15-1-pve-local-ssd:subvol-146-disk-1,size=15G',
         'cpuunits': 1024,
         'net0': 'name=eth0,bridge=...', 'swap': 0, 'cpulimit': '2',
         'hostname': 'acme-tech-stats', 'ostype': 'ubuntu',
         'digest': '774faa099d28c4953462f3de13742c228d593aaf'}

        or:

        {'memory': 8192, 'net0': 'virtio=...,bridge=vmbr...',
         'ide2': 'none,media=cdrom', 'ostype': 'win10',
         'name': 'acme-tech-web02-2019',
         'scsi2': 'mc15-1-pve-local-ssd:vm-152-disk-3,size=50G',
         'digest': 'dfe18d52510cbfb76e0a06247dc29ed737ca2d17',
         'bootdisk': 'scsi0',
         'scsi1': 'mc15-1-pve-local-ssd:vm-152-disk-2,size=100G',
         'cores': 2, 'scsi0': 'mc15-1-pve-local-ssd:vm-152-disk-1,size=50G',
         'sockets': 1, 'ide0': 'none,media=cdrom', 'numa': 0,
         'scsihw': 'virtio-scsi-pci',
         'smbios1': 'uuid=e4213e79-1989-....-....-............',
         'boot': 'dcn'}
        """
        api_vm = getattr(self.cluster._api.nodes(self.node), self.type)(
            self.vmid)
        vm_config = api_vm.config.get()

        boot_disk = vm_config.pop('bootdisk', None)
        if boot_disk:
            boot_volume = vm_config.pop(boot_disk)
            yield PveGuestVolume(
                self.cluster, guest=self, driver=boot_disk, info=boot_volume,
                is_boot=True)
        else:
            log.warn('No bootdisk for %s', self)

        for key, value in vm_config.items():
            if (key.startswith(('ide', 'sata', 'scsi', 'virtio')) and
                    key[-1].isdigit()):
                yield PveGuestVolume(
                    self.cluster, guest=self, driver=key, info=value)

    def __repr__(self):
        """
        MYCLUSTER/qemu/111/acme-tech-win02-OFF(OFF)
        """
        return (
            '{cluster.name}/{o.type}/{o.vmid}/{o.name}'
            '({on})').format(
                cluster=self.cluster, o=self,
                on=('on' if self.is_running else 'OFF'))


class PveGuestVolume:
    def __init__(self, cluster, guest, driver, info, is_boot=False):
        self.cluster = cluster
        self.guest = guest
        self.driver = driver
        self.is_boot = is_boot

        # Parse: 'mc15-1-pve-local-ssd:vm-152-disk-3,size=50G'
        # Parse: 'none,media=cdrom'
        if ',' in info:
            storage, info = info.split(',', 1)
        else:
            storage, info = storage, ''
        if ':' in storage:
            storage, volume = storage.split(':', 1)
        else:
            volume = None
        if storage == 'none' and volume is None:
            storage = None

        self.name = volume
        self.info = info
        self.is_removable = ('media=cdrom' in info.split(','))

        if self.is_removable:
            self.filestore = self.cluster.get_filestore(None)
            self.is_enabled = False
        else:
            self.filestore = self.cluster.get_filestore(storage)
            self.is_enabled = self.filestore.is_enabled

    def __repr__(self):
        """
        MYCLUSTER/zfspool/mc15-1-pve-local-ssd/vm-152-disk-1(vm=152;BOOT)
        """
        if self.is_boot:
            extra = ';BOOT'
        else:
            extra = ''

        return (
            '{cluster.name}/{f.type}/{f.name}/{o.name}'
            '(vm={g.vmid}{extra})').format(
                cluster=self.cluster, f=self.filestore, o=self, g=self.guest,
                extra=extra)
