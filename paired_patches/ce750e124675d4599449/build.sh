#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/pvrusb2/pvrusb2-context.o
