#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/mpls/af_mpls.o
