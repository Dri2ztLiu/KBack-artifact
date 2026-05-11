#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/usb/misc/chaoskey.o
