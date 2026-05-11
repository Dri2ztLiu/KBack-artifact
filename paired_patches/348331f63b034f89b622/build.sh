#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/input/mouse/bcm5974.o
