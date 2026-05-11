#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bluetooth/hci_core.o net/bluetooth/mgmt.o include/net/bluetooth/
