#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/em28xx/em28xx-dvb.o
