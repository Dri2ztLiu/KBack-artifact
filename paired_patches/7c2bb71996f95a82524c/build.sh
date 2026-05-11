#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/hid/usbhid/hid-core.o include/linux/
