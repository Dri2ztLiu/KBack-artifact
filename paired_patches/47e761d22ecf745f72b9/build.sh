#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ipv6/ila/ila_xlat.o
