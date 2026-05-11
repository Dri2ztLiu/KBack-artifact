#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/tty/n_gsm.o
