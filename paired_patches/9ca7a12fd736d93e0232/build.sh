#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/radio/si470x/radio-si470x-usb.o
