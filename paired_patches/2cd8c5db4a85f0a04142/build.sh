#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/dvb-usb/az6027.o
