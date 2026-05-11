#!/bin/sh
set -e
make allyesconfig
make -j `nproc` sound/usb/usx2y/usbusx2y.o
