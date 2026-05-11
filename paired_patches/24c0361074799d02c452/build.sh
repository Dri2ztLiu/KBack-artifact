#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/hid/hid-cougar.o
