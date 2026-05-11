#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/qrtr/qrtr.o
