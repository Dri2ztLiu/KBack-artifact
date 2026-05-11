#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/usb/gadget/udc/dummy_hcd.o
