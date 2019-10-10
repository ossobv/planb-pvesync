planb-pvesync
=============

*Standalone CLI tool to work with Proxmox VE ZFS volumes and sync them to
local storage.*

I.e. convenient ZVOL backup to a separate backup system, using ZFS snapshots on
local and remote.

Additionally, *planb-pvesync* will -- not right now, but shortly -- provide an
integration with `PlanB <https://github.com/ossobv/planb>`_ so *Proxmox VE*
disks will be auto-detected, and added to the *PlanB* backup routine.

.. warning:: **WARNING**

    *Be warned. This software is in development/alpha stage, and the interface
    and configuration syntax are likely to change.*


Command line examples
---------------------

Short help:

.. code-block:: console

    $ planb-pvesync -h
    usage: planb-pvesync [-h] [--config FILENAME] [--pve-cluster CLUSTERNAME]
        [--pve-guest GUESTNAME] [--sync-zfs-root DEST_FILESYSTEM]
        {list-pve-hosts,list-pve-guests,list-pve-filestores,sync-pve-guest}
    planb-pvesync: error: the following arguments are required: command

Listing of PVE nodes (VM hosts):

.. code-block:: console

    $ planb-pvesync -p MYCLUSTER list-pve-hosts
    MYCLUSTER/node/mc10-5-pve
    MYCLUSTER/node/mc15-1-pve

Listing of PVE filestorage nodes:

.. code-block:: console

    $ planb-pvesync -p MYCLUSTER list-pve-filestores
    MYCLUSTER/dir/mc10-5-pve-local-iso(on;('/var/lib/iso', None))
    MYCLUSTER/dir/mc15-1-pve-local-iso(on;('/var/lib/iso', None))
    MYCLUSTER/zfspool/mc10-5-pve-local-ssd(on;(None, 'rpool/data/images')) \
        run_remote_args=['ssh', 'planb@10.20.30.105']
    MYCLUSTER/zfspool/mc15-1-pve-local-ssd(on;(None, 'rpool/data/images')) \
        run_remote_args=['ssh', 'planb@10.20.30.151']

Listing of virtual machines (VM guests):

.. code-block:: console

    $ planb-pvesync -p MYCLUSTER list-pve-guests
    MYCLUSTER/qemu/106/acme-backend-wp(on)
      MYCLUSTER/zfspool/mc15-1-pve-local-ssd/vm-106-disk-1(vm=106;BOOT) \
        run_remote_args=['ssh', 'planb@10.20.30.151']
    ...

Backup/sync of remote filesystems from VM guest 106 to local ZFS filesystem
below ``tank/enc``:

.. code-block:: console

    $ planb-pvesync -p MYCLUSTER sync-pve-guest -g 106 --sync-zfs-root tank/enc
    ...
    ['/bin/sh', '-c', "ssh planb@10.20.30.151 \
      'sudo zfs send -i \
       rpool/data/images/vm-106-disk-1@daily-201910100721 \
       rpool/data/images/vm-106-disk-1@daily-201910101123 | qlzip1' | \
      qlzcat1 | pv -ptebar -B512M -w72 -s1895440816 | \
      sudo zfs recv tank/enc/acme-backend-wp/mc15-1-pve-local-ssd--vm-103-disk-1"]
    1.81GiB 0:00:12 [ 148MiB/s] [ 148MiB/s] [============>] 102%

The Python code assembles the appropriate ssh + sudo + zfs-send/recv commands,
detecting new filesystems, new snapshots and syncing them as appropriate.

(The *102%* is because the sync size is an estimate only.)


Configuration
-------------

Config ``~/.proxmoxrc`` (similar to Proxmove config)::

    [pve:MYCLUSTER]
    api=https://planb@pve:PASS:cluster.example.com:443

      [storage:MYCLUSTER:mc10-5-pve-local-ssd]
      ssh=someuser@10.20.30.105

      [storage:MYCLUSTER:mc15-1-pve-local-ssd]
      ssh=someuser@10.20.30.151

We assume:

- we're using *sudo* both locally and remotely (allow all ``/sbin/zfs`` with
  ``NOPASSWD``);
- we have *qlzip1* and *qlzcat1* available on both ends (see `qpress-deb
  <https://github.com/ossobv/qpress-deb>`_);
- *pv* is available locally, for a bit of buffering and verbosity during data
  transfer.


Some notes about (local) ZFS encryption
---------------------------------------

ZFS encryption is new in ZoL 0.8.x. On *Ubuntu* this is available in *Eoan
Ermine* (19.10).

Enabling encryption on the pool ``tank``.

.. code-block:: console

    # zpool set feature@encryption=enabled tank

Initially, we'll go with single-key encryption on the entire pool, and mount it
on ``/tank``. Use a strong key and store it safely. (We'll want to gain some
experience with it before doing per-filesystem encryption.)

*OBSERVE: Using the 'tank/enc' child filesystem and not 'tank' directly, for
reasons explained in* `don't encrypt the pool root
<https://www.reddit.com/r/zfs/comments/bnvdco/zol_080_encryption_dont_encrypt_the_pool_root/>`_.

.. code-block:: console

    # zfs create -o encryption=aes-256-gcm \
        -o keyformat=passphrase -o keylocation=prompt \
        -o mountpoint=/tank/enc tank/enc

You'll need it *after reboot* (after ``zpool import``). The filesystem list is
readable, but the contents nor zvols will be available until the key is
loaded.

.. code-block:: console

    # ls -l /dev/zvol
    ls: cannot access '/dev/zvol': No such file or directory

    # zfs load-key tank/enc
    Enter passphrase for 'tank/enc':

    # ls -l /dev/zvol
    ...

After ``tank/enc`` creation, you can consider moving it to ``/tank``, for
sanity. Note that this is mostly irrelevant if you're only going to sync zvols.
You won't mount those anyway:

.. code-block:: console

    # umount /tank/enc /tank
    # zfs set mountpoint=none tank
    # zfs set mountpoint=/tank tank/enc

    # zfs list -o name,used,avail,refer,encryptionroot,mountpoint -S encryptionroot
    NAME       USED  AVAIL     REFER  ENCROOT   MOUNTPOINT
    tank/enc   366K   134T      366K  tank/enc  /tank
    tank      2.49M   134T      238K  -         none

*BEWARE: Do remember to reference the ZFS filesystem with 'tank/enc', even though
the mountpoint has no '/enc'.*


planb-pvesync TODOs
-------------------

* Remove FIXMEs :)
* Auto-add -c aes128-gcm@openssh.com for speed (when cpus have 'aes')?
  Or.. replace the 'ssh' with a 'rsh'? Or allow a rsh in DEFAULT to be set for
  'ssh -c aes128-gcm@openssh.com'. In that case we should replace 'ssh=' with
  'dest='.  Perhaps use a 'url=ssh://user@host' and optional 'ssh=ssh -c
  aes128-gcm@openssh.com'.  In any case, using aes128-gcm@openssh.com appears
  to use 40% cpu compared to default chacha20-poly1305@openssh.com, a pretty
  good improvement.
* Add sync-filesystem command with met SRC en DST params (bypassing all
  --pve-stuff).
* Add verbose/debug mode through python logging (helps for instance for
  failures when we need -F to zfs-recv to "correct" failing filesystem asyncs).
* Make the pv(1) pipe-view optional (if isatty()==0?).
* Steal check_output from planb.subprocess2?
* Refactor send_snapshot_command/size, removing duplicate code.
* Think about how many snapshots we'll want to keep on remote (>1 is nice to
  have, so we can fall back to an earlier version if we lose a snapshot on
  either side). Obviously keeping to many will eat disk on the source FS.
* Add monthly snapshots locally? (Won't be needed when we do multu-purpose
  snapshot names (without daily/monthly) like we intended for PlanB. (And are
  we allowed to add snaps? Or will the sync complain/break?)
* Make -p optional (if there is only one cluster..?).
* CAVEAT: If you start an initial sync and a snapshot exists already -- if that
  snapshot is old, you'll likely have a long 2nd sync run. Keep this in mind
  when doing initial syncs (do a 2nd one immediately after?). (Document?)
