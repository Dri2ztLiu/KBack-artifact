#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/qrtr/af_qrtr.o
