#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/bluetooth/hci_ldisc.o drivers/bluetooth/hci_serdev.o
