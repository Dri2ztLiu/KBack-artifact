#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/tty/tty_ldisc.o drivers/tty/vt/vt.o include/linux/
