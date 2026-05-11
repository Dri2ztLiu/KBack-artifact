#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/infiniband/ulp/srp/ib_srp.o
