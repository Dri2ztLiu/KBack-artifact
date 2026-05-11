#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/can/bcm.o
