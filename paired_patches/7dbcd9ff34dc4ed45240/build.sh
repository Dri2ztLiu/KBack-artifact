#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/usb/core/message.o
