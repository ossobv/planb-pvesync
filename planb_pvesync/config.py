from configparser import ConfigParser
from os import path
from urllib.parse import urlparse


class ConfigFile:
    """
    Example .proxmoxrc file:

      [pve:acme_cluster]
      api=https://USER:PASS@HOST:PORT

        [storage:acme_cluster:storage_x]
        ssh=user@host

        [storage:acme_cluster:storage_y]
        ssh=user@host2

      [pve:acme_cluster2]
      api=https://USER:PASS@HOST:PORT

    Example usage:

      config = ConfigFile('~/.proxmoxrc')
      pveconf = config.get_pve_config('acme_cluster')

    """
    def __init__(self, filename):
        self._filename = path.expanduser(filename)  # ~ => $HOME
        self._parser = ConfigParser(
            # same args as proxmove supplies..
            interpolation=None, inline_comment_prefixes=('#', ';'),
            empty_lines_in_values=False)
        with open(self._filename) as fp:
            self._parser.read_file(fp)
        pve_keys = [i for i in self._parser.sections() if i.startswith('pve:')]
        if not pve_keys:
            raise ValueError('expected one or more [pve:CLUSTERNAME] sections')

    def get_pve_config(self, cluster_name):
        try:
            cluster_conf = self._parser['pve:{}'.format(cluster_name)]
        except KeyError:
            raise ValueError('missing [pve:{}] in config'.format(cluster_name))

        pve_config = PveConfig(cluster_name, cluster_conf)
        self._set_pve_filestore_remote_access(pve_config, cluster_name)
        return pve_config

    def _set_pve_filestore_remote_access(self, pve_config, cluster_name):
        storage_prefix = 'storage:{}:'.format(cluster_name)
        storage_sections = [
            i for i in self._parser.sections() if i.startswith(storage_prefix)]
        for section in storage_sections:
            storage_const, cluster_const, name = section.split(':')
            data = self._parser[section]
            access = PveFilestoreRemoteAccess(ssh=data['ssh'])
            pve_config.set_filestore_remote_access(name, access)


class PveConfig:
    def __init__(self, cluster_name, cluster_conf):
        self._cluster_name = cluster_name
        self._cluster_conf = cluster_conf
        self._apiurl = cluster_conf['api']
        if not self._apiurl.startswith('https://'):
            raise ValueError('bad API url in [pve:{}]'.format(
                self._cluster_name))
        self._filestore_remote_access = {}

    def get_filestore_remote_access(self, name):
        return self._filestore_remote_access[name]

    def set_filestore_remote_access(self, name, filestore_remote_access):
        assert name not in self._filestore_remote_access, name
        self._filestore_remote_access[name] = filestore_remote_access

    @property
    def host(self):
        obj = urlparse(self._apiurl)
        return obj.hostname

    @property
    def port(self):
        obj = urlparse(self._apiurl)
        if obj.port:
            port = int(obj.port)
        elif obj.scheme == 'https':
            port = 443
        elif obj.scheme == 'http':
            port = 80
        else:
            raise NotImplementedError(self._apiurl)
        return port

    @property
    def user(self):
        obj = urlparse(self._apiurl)
        return obj.username

    @property
    def password(self):
        obj = urlparse(self._apiurl)
        return obj.password

    @property
    def verify_ssl(self):
        return True


class PveFilestoreRemoteAccess:
    def __init__(self, ssh):
        self.run_remote_args = [
            # The aes128-gcm@openssh.com _may_ be faster if both CPUs support
            # it (lowered ssh(d) cpu-time).
            'ssh', '-c', 'aes128-gcm@openssh.com', ssh]  # user@host

    def __repr__(self):
        return 'run_remote_args={!r}'.format(self.run_remote_args)
