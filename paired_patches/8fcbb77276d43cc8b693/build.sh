#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/infiniband/core/cma.o
