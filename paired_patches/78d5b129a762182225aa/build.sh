#!/bin/sh
set -e
make allyesconfig
make -j `nproc` sound/usb/mixer.o
