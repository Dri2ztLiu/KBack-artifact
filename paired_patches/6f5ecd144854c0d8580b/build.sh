#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/staging/rtl8712/usb_intf.o
