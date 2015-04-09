#!/usr/bin/env python
# Copyright (c) 2014 - 2015 EMC Corporation, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""
The script to clean up the iSCSI multipath faulty devices

Version history:
    0.1.0 - Initial version
    0.1.1 - More robust support of SQL connection info
    0.1.2 - Use nova.db.sqlalchemy instead of MySQLdb for DB access
    0.1.3 - Add more meaningful output
"""

import glob
import json
import os
import re
import string
import sys

from oslo.config import cfg

from nova import context
from nova.db.sqlalchemy import api as db_api
from nova.db.sqlalchemy import models
from nova import utils

CONF = cfg.CONF


def usage():
    print("""
Usage:
    python %s --config-file /etc/nova/nova.conf [--detection-only]

Note: This script intends to clean up the iSCSI multipath faulty devices
hosted by VNX Block Storage.""" % sys.argv[0])


class FaultyDevicesCleaner(object):
    def __init__(self, detection_only=False):
        self.detection_only = detection_only
        self.faulty_device_num = 0
        self.faulty_path_num = 0
        self.faulty_devices = []
        # Get host name of Nova computer node.
        self.host_name = self._get_host_name()

    def _get_host_name(self):
        (out, err) = utils.execute('hostname')
        return out

    def _get_ncpu_emc_target_info_list(self):
        target_info_list = []
        # Find the targets used by VM on the compute node
        bdms = db_api.model_query(context.get_admin_context(),
                                  models.BlockDeviceMapping,
                                  session=db_api.get_session())
        bdms = bdms.filter(models.BlockDeviceMapping.connection_info != None)
        bdms = bdms.join(models.BlockDeviceMapping.instance).filter_by(
            host=string.strip(self.host_name))

        for bdm in bdms:
            conn_info = json.loads(bdm.connection_info)

            if 'data' in conn_info:
                if 'target_iqns' in conn_info['data']:
                    target_iqns = conn_info['data']['target_iqns']
                    target_luns = conn_info['data']['target_luns']
                elif 'target_iqn' in conn_info['data']:
                    target_iqns = [conn_info['data']['target_iqn']]
                    target_luns = [conn_info['data']['target_lun']]
                else:
                    target_iqns = []
                    target_luns = []
                for target_iqn, target_lun in zip(target_iqns, target_luns):
                    if 'com.emc' in target_iqn:
                        target_info = {
                            'target_iqn': target_iqn,
                            'target_lun': target_lun,
                        }
                        target_info_list.append(target_info)

        return target_info_list

    def _get_ncpu_emc_target_info_set(self):
        target_info_set = set()
        for target_info in self._get_ncpu_emc_target_info_list():
            target_iqn = target_info['target_iqn']
            target_lun = target_info['target_lun']
            target_info_key = "%s-%s" % (target_iqn.rsplit('.', 1)[0],
                                         target_lun)
            # target_iqn=iqn.1992-04.com.emc:cx.fnm00130200235.a7
            # target_lun=203
            # target_info_key=iqn.1992-04.com.emc:cx.fnm00130200235-203
            target_info_set.add(target_info_key)
        return target_info_set

    def _get_target_info_key(self, path):
        temp_tuple = path.split('-lun-', 1)
        target_lun = temp_tuple[1]
        target_iqn = temp_tuple[0].split('-iscsi-')[1]
        target_info_key = "%s-%s" % (target_iqn.rsplit('.', 1)[0], target_lun)
        # path=/dev/disk/by-path/ip-192.168.3.52:3260-iscsi-iqn.1992-
        # 04.com.emc:cx.fnm00130200235.a7-lun-203
        # target_info_key=iqn.1992-04.com.emc:cx.fnm00130200235-203
        return target_info_key

    def _get_non_ncpu_target_info_map(self):
        # Group the paths by target_info_key
        ncpu_target_info_set = self._get_ncpu_emc_target_info_set()
        device_paths = self._get_emc_device_paths()
        target_info_map = {}
        for path in device_paths:
            target_info_key = self._get_target_info_key(path)
            if target_info_key in ncpu_target_info_set:
                continue
            if target_info_key not in target_info_map:
                target_info_map[target_info_key] = []
            target_info_map[target_info_key].append(path)
        return target_info_map

    def _all_related_paths_faulty(self, paths):
        for path in paths:
            real_path = os.path.realpath(path)
            out, err = self._run_multipath(['-ll', real_path],
                                           run_as_root=True,
                                           check_exit_code=False)
            if 'active ready' in out:
                # At least one path is still working
                return False
        return True

    def _delete_all_related_paths(self, paths):
        for path in paths:
            real_path = os.path.realpath(path)
            device_name = os.path.basename(real_path)
            device_delete = '/sys/block/%s/device/delete' % device_name
            if os.path.exists(device_delete):
                # Copy '1' from stdin to the device delete control file
                utils.execute('cp', '/dev/stdin', device_delete,
                              process_input='1', run_as_root=True)
                print("Info: Deleted faulty iSCSI path %s." % path)
            else:
                print("Warning: Unable to delete %s." % real_path)

    def _cleanup_faulty_paths(self):
        non_ncpu_target_info_map = self._get_non_ncpu_target_info_map()
        for paths in non_ncpu_target_info_map.itervalues():
            if self._all_related_paths_faulty(paths):
                if self.detection_only:
                    self.faulty_path_num += len(paths)
                    # Check next without deleting the paths
                    continue
                self._delete_all_related_paths(paths)
        if self.detection_only:
            print("Info: Found %s faulty iSCSI paths to be deleted."
                  % self.faulty_path_num)

    def _cleanup_faulty_dm_devices(self):
        out_ll, err_ll = self._run_multipath(['-ll'],
                                             run_as_root=True,
                                             check_exit_code=False)
        # Pattern to split the dm device contents as follows
        #     Each section starts with a WWN and ends with a line with
        #     "  `-" as the prefix
        #
        # 3600601601bd032007c097518e96ae411 dm-2 ,
        # size=1.0G features='1 queue_if_no_path' hwhandler='1 alua' wp=rw
        # `-+- policy='round-robin 0' prio=0 status=active
        #   `- #:#:#:# -   #:#   active faulty running
        # 36006016020d03200bb93e048f733e411 dm-0 DGC,VRAID
        # size=1.0G features='1 queue_if_no_path' hwhandler='1 alua' wp=rw
        # |-+- policy='round-robin 0' prio=130 status=active
        # | |- 3:0:0:2 sdd 8:48  active ready  running
        # | `- 5:0:0:2 sdj 8:144 active ready  running
        # `-+- policy='round-robin 0' prio=10 status=enabled
        #   |- 4:0:0:2 sdg 8:96  active ready  running
        #   `- 6:0:0:2 sdm 8:192 active ready  running
        dm_pat = r'([0-9a-fA-F]{30,})[^\n]+,[^\n]*\n[^,]*  `-[^\n]*'
        dm_m = re.compile(dm_pat)
        path_pat = r'- \d+:\d+:\d+:\d+ '
        path_m = re.compile(path_pat)
        for m in dm_m.finditer(out_ll):
            if self.detection_only:
                if not ('active ready' in m.group(0)):
                    self.faulty_device_num += 1
                    self.faulty_devices.append(m.group(1))
                    continue
            if not path_m.search(m.group(0)):
                # Only #:#:#:# remain in the output, all the paths of the dm
                # device should have been deleted. No need to keep the device
                out_f, err_f = self._run_multipath(['-f', m.group(1)],
                                                   run_as_root=True,
                                                   check_exit_code=False)
                if "map in use" in out_f + err_f:
                    print("Warning: Could not flush "
                          "faulty multipath device %s."
                          % m.group(1))
                    print("Info: Please retry later "
                          "or execute 'dmsetup message %s 0 fail_if_no_path' "
                          "before retrying."
                          % m.group(1))
                else:
                    print("Info: Deleted faulty multipath device %s."
                          % m.group(1))

        if self.detection_only:
            print("Info: Found %s multipath faulty devices to be deleted."
                  % self.faulty_device_num)
            for fdm in self.faulty_devices:
                print("Info: %s is faulty." % fdm)

    def cleanup(self):
        self._cleanup_faulty_paths()
        # Make sure the following configuration is in /etc/multipath.conf
        # Otherwise, there may be "map in use" failure when deleting
        # dm device
        #
        # defaults {
        #   flush_on_last_del yes
        # }
        #
        self._cleanup_faulty_dm_devices()

    def _get_emc_device_paths(self):
        # Find all the EMC iSCSI devices under /dev/disk/by-path
        # except LUNZ and partition reference
        pattern = '/dev/disk/by-path/ip-*-iscsi-iqn*com.emc*-lun-*'
        device_paths = [path for path in glob.glob(pattern)
                        if ('lun-0' not in path and '-part' not in path)]
        return device_paths

    def _run_multipath(self, multipath_command, **kwargs):
        check_exit_code = kwargs.pop('check_exit_code', 0)
        (out, err) = utils.execute('multipath',
                                   *multipath_command,
                                   run_as_root=True,
                                   check_exit_code=check_exit_code)
        if ('debug' in CONF and CONF.debug) or False:
            print(("Debug: multipath %(command)s\n"
                   "stdout=\n%(out)s\n"
                   "stderr=\n%(err)s")
                  % {'command': multipath_command,
                     'out': out,
                     'err': err})

        return out, err


def main():
    if len(sys.argv) < 3 or sys.argv[1] != '--config-file':
        usage()
        exit(1)
    detection_only = False
    if '--detection-only' in sys.argv:
        detection_only = True
        sys.argv.remove('--detection-only')

    out, err = utils.execute('which', 'multipath', check_exit_code=False)
    if 'multipath' not in out:
        print('Info: Multipath tools not installed. No cleanup need be done.')
        exit(0)

    multipath_flush_on_last_del = False
    multipath_conf_path = "/etc/multipath.conf"
    if os.path.exists(multipath_conf_path):
        flush_on_last_del_yes = re.compile(r'\s*flush_on_last_del.*yes')
        for line in open(multipath_conf_path, "r"):
            if flush_on_last_del_yes.match(line):
                multipath_flush_on_last_del = True
                break
    if not multipath_flush_on_last_del:
        print("Warning: 'flush_on_last_del yes' is not seen in"
              " /etc/multipath.conf."
              " 'map in use' failure may show up during cleanup.")

    CONF(sys.argv[1:])

    # connect_volume and disconnect_volume in nova/virt/libvirt/volume.py
    # need be adjusted to take the same 'external=True' lock for
    # synchronization
    @utils.synchronized('connect_volume', external=True)
    def do_cleanup(detection_only):
        cleaner = FaultyDevicesCleaner(detection_only)
        cleaner.cleanup()
    do_cleanup(detection_only)

if __name__ == "__main__":
    main()
