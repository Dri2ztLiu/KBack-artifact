#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/bluetooth/hci_h5.o
