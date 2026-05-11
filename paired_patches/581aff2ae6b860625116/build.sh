#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/sctp/input.o
