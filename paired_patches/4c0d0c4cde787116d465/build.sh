#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bluetooth/af_bluetooth.o net/bluetooth/sco.o include/net/bluetooth/
