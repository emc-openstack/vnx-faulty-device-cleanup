# Faulty Device Cleanup Script for VNX

Copyright (c) 2014 - 2015 EMC Corporation, Inc.
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
This is a script to clean up iSCSI multipath faulty devices.

Some iSCSI multipath faulty devices may show up due to some unexpected timeout or some operations out of synchronization. Too many faulty devices may result in high CPU consumption and affect the system performance.
It is difficult for OpenStack common logic to avoid faulty devices in all corner cases. And either in VNX side or VNX Cinder Driver side, it is also impossible to completely avoid the faulty device issue under current architecture. As a workaround, this external helper script is created to clean up the iSCSI multipath faulty devices.

* This script only support iSCSI storage from VNX array
* The usage is `faulty_device_cleanup.py --config-file /etc/nova/nova.conf`
* Current implementation has dependency on some OpenStack-specific modules (such as nova.utils and oslo.config) and DB-related module (such as MySQLdb.DataBase).
* The script will use the `sql_connection` or `database.connection` in `/etc/nova/nova.conf` to query Nova DB to decide whether a faulty device is still in use.
* MySQL is the only supported DB so far.
* It is recommended to use `flush_on_last_del yes` in `defaults` section of `/etc/multipath.conf`. Otherwise `map in use` failure may come out during cleanup and delay the deletion of multipath faulty devices

