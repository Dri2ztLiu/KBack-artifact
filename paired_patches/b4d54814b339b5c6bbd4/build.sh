#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/zr364xx/zr364xx.o
