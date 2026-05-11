#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/llc/llc_core.o include/net/
