# Faulty Device Cleanup Script for VNX

Copyright (c) 2014 EMC Corporation, Inc.
All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License"); you may
not use this file except in compliance with the License. You may obtain
a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations
under the License.


## Overview
This is the script to cleanup iSCSI multipath faulty devices on Nova Compute nodes.


Some iSCSI multipath faulty devices may show up in Nova Compute node due to some unexpected timeout or operations out of synchronization. Too many faulty devices may result in high CPU consumption and affect the system performance.
It is difficult for Nova to avoid faulty devices in all corner cases. And in VNX side or VNX Cinder Driver side, it is also impossible to completely avoid the faulty device issue in current architecture. Thus, as a workaround, this script is created to cleanup the iSCSI multipath faulty devices besides the VNX Cinder Driver

* This script only support iSCSI storage from VNX array
* This script should be used on Nova Compute nodes
* The script usage is `faulty_device_cleanup.py --config-file /etc/nova/nova.conf`
* This script will use the `sql_connection` in `/etc/nova/nova.conf` to access Nova DB. And MySQL is the only supported DB so far
* It is suggested to use `flush_on_last_del yes` in `defaults` section of `/etc/multipath.conf`. Otherwise `map in use` failure may come out during cleanup and delay the deletion of multipath faulty devices

