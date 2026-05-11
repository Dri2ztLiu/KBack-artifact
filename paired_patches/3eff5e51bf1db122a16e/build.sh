#!/bin/sh
set -e
make allyesconfig
make -j `nproc` crypto/scompress.o
