#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/can/isotp.o
