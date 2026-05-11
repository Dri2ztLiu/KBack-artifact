#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/input/misc/uinput.o
