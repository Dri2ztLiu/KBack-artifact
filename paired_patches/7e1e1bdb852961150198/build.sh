#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/smc/af_smc.o
