#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/usb/asix_common.o
