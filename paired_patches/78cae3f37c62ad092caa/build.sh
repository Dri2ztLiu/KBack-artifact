#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/usb/rtl8150.o
