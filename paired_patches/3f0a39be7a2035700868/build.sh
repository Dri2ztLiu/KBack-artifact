#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bluetooth/hci_conn.o net/bluetooth/hci_sync.o include/net/bluetooth/
