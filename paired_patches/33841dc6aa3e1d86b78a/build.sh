#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ax25/af_ax25.o
