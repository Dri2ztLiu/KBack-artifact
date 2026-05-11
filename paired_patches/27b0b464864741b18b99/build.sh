#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/siano/smsusb.o
