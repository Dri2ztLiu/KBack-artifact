#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/caif/caif_serial.o
