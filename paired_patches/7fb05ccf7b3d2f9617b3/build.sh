#!/bin/sh
set -e
make allyesconfig
make -j `nproc` sound/usb/line6/driver.o
