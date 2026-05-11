#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bluetooth/hci_core.o net/bluetooth/hci_sock.o net/bluetooth/hci_sysfs.o include/net/bluetooth/
