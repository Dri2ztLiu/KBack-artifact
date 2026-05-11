#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/nfc/pn533/usb.o
