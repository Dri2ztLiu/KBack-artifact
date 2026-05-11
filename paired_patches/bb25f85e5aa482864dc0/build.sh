#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/airspy/airspy.o
