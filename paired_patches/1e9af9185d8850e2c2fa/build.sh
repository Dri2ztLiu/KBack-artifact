#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/key/af_key.o
