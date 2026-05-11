#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/tty/vt/vt.o
