#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/usb/sierra_net.o
