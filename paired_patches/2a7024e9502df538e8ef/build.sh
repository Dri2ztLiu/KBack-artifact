#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/llc/af_llc.o
