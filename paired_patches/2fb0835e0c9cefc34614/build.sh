#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bluetooth/hci_core.o net/bluetooth/iso.o net/bluetooth/l2cap_core.o net/bluetooth/rfcomm/core.o net/bluetooth/sco.o include/net/bluetooth/
