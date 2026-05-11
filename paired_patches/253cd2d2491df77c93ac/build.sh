#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/wireless/scan.o
