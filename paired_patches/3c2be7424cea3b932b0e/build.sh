#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/dvb-usb/dvb-usb-init.o
