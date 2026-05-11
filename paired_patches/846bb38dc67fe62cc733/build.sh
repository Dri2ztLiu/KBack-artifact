#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/ethernet/intel/e1000/e1000_main.o
