#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/sctp/ipv6.o
