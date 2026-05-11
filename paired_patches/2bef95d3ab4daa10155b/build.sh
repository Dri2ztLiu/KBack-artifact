#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bluetooth/sco.o
