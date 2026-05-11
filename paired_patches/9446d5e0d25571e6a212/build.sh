#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/uvc/uvc_status.o
