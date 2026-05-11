#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bluetooth/hci_core.o net/bluetooth/hci_event.o include/net/bluetooth/
