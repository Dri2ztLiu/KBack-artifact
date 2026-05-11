#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/atm/lec.o
