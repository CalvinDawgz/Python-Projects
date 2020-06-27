#!/usr/bin/env python

import os
import sys
import pprint
from netaddr import *
import pynetbox
import csv
from jinja2 import Template

try:
    assert all(os.environ[env] for env in ['NETBOX_TOKEN'])
except KeyError as exc:
    sys.exit(f"ERROR: missing ENVAR: {exc}")

NETBOX_URL = "http://localhost:8000"
NETBOX_TOKEN = os.environ['NETBOX_TOKEN']

nb = pynetbox.api(url=NETBOX_URL, token=NETBOX_TOKEN)

### Read from CSV for NetBox device data
nb_source_file = "nb_devices.csv"

nb_all_devices = list()
nb_all_devices_primaryIPs = dict()

# Stores IPs for duplicate checking
all_IPs = list()

# Stores non-existent NetBox objects defined in CSV
nb_non_existent_count = 0
nb_non_existent_objects = dict()
nb_non_existent_objects['site'] = list()
nb_non_existent_objects['device_type'] = list()
nb_non_existent_objects['device_role'] = list()
nb_non_existent_objects['rack'] = list()

fmt = "{:<15}{:<25}{:<15}"
header = ("Model","Name","Status")

try:
    with open(nb_source_file) as f:
      reader = csv.DictReader(f)
      for row in reader:
          ndev_site = nb.dcim.sites.get(slug=row['site'])
          ndev_dtype = nb.dcim.device_types.get(slug=row['device_type'])
          ndev_drole = nb.dcim.device_roles.get(slug=row['device_role'])
          ndev_rack = nb.dcim.racks.get(q=row['rack'])

          # Verifies whether DCIM object exists
          if (not ndev_site):
              nb_non_existent_objects['site'].append(row['site'])
              nb_non_existent_count += 1
          if (not ndev_dtype):
              nb_non_existent_objects['device_type'].append(row['device_type'])
              nb_non_existent_count += 1
          if (not ndev_drole):
              nb_non_existent_objects['device_role'].append(row['device_role'])
              nb_non_existent_count += 1
          if (not ndev_rack):
              nb_non_existent_objects['rack'].append(row['rack'])
              nb_non_existent_count += 1

          # Generates dict of values for PyNetbox to create object
          if (nb_non_existent_count == 0):
              nb_all_devices.append(
                dict(
                    name=row['name'],
                    site=ndev_site.id,
                    device_type=ndev_dtype.id,
                    device_role=ndev_drole.id,
                    rack=ndev_rack.id,
                    face=row['face'],
                    position=row['position'],
                    serial=row['serial'],
                    asset_tag=row['asset_tag'],
                    status=row['status'],
                )
              )

              nb_all_devices_primaryIPs[row['name']] = row['primary_ipv4']
              all_IPs.append(row['primary_ipv4'])

except FileNotFoundError as e:
    print(e)
except pynetbox.core.query.RequestError as e:
    print(e.error)

flag = len(set(all_IPs)) == len(all_IPs)

### Generates table of non-existent NetBox objects defined in CSV
if ( (nb_non_existent_count > 0) or not(flag) ):
    # Print results of verifying duplicated IPs
    if(not flag):
        print()
        print(12*"*"," Verify for duplicated IPs ",12*"*")
        print ("One or more of the devices have duplicated IPs")

    print()
    print(12*"*"," Verify the following NetBox Objects ",12*"*")
    print(fmt.format(*header))

    # Print summary of non-existent objects in CSV
    for model,nb_objects in nb_non_existent_objects.items():
        for nb_object in nb_objects:
            print(
                fmt.format(
                    model,
                    nb_object,
                    "Non-Existent"
                )
            )
else:
    try:
        # Retrieve device object by name and delete
        for dev in nb_all_devices:
            dev = nb.dcim.devices.get(name=dev['name'])
            dev.delete()

        # Add devices to NetBox and store resulting object in "created_devs"
        nb_created_devices = nb.dcim.devices.create(nb_all_devices)

        # Formatting and header for output
        fmt = "{:<15}{:<20}{:<15}{:<10}{:<15}{:<25}{:<20}"
        header = ("Device", "Dev Role", "Dev Type", "Site", "Rack", "Management Interface", "IP")
        print()
        print(50*"*"," Created Devices ",50*"*")
        print(fmt.format(*header))

        for created_dev in nb_created_devices:
            # Retrieve specific interface associated w/ created device
            nb_primary_interface = nb.dcim.interfaces.filter(device=created_dev.name,name="FastEthernet0/0")

            # Create dict to store attributes for device's primary IP
            primary_ip_addr_dict = dict(
                address=nb_all_devices_primaryIPs[created_dev.name],
                status=1,
                description="Management IP for {}".format(created_dev.name),
                interface=nb_primary_interface[0].id,
            )

            # Create primary IP and assign to device's first interface
            new_primary_ip = nb.ipam.ip_addresses.create(primary_ip_addr_dict)

            # Retrieves created device, and sets the primary IP for the device
            dev = nb.dcim.devices.get(created_dev.id)
            dev.primary_ip4 = new_primary_ip.id
            dev.save()

            # Print summary info for each created device
            print(
                fmt.format(
                    created_dev.name,
                    created_dev.device_role.name,
                    created_dev.device_type.model,
                    created_dev.site.name,
                    created_dev.rack.name,
                    nb_primary_interface[0].name,
                    new_primary_ip.address
                )
            )

    except pynetbox.core.query.RequestError as e:
        print(e.error)
