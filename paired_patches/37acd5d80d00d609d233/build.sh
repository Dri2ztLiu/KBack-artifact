#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bluetooth/hci_conn.o
