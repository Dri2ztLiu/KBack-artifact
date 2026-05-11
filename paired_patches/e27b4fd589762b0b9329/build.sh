#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/dvb-usb/dibusb-common.o
