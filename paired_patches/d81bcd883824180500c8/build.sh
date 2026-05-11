#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/dsa/user.o
