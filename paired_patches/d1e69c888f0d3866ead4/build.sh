#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/cpia2/cpia2_core.o drivers/media/usb/cpia2/cpia2_usb.o drivers/media/usb/cpia2/
