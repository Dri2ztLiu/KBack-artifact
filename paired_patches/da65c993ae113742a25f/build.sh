#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/llc/llc_s_ac.o
