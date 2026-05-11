#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/wireless/ocb.o
