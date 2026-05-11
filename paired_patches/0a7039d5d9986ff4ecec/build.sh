#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bluetooth/hci_core.o net/bluetooth/mgmt.o net/bluetooth/mgmt_util.o include/net/bluetooth/ net/bluetooth/
