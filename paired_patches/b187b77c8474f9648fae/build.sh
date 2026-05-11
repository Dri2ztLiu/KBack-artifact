#!/bin/sh
set -e
make allyesconfig
make -j `nproc` crypto/pcrypt.o
