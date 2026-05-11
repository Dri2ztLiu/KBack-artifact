#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/gspca/cpia1.o
