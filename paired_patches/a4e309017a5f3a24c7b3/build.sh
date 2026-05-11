#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/gspca/sq905.o
