#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/caif/caif_usb.o
