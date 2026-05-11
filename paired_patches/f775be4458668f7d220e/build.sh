#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/smc/smc_inet.o
