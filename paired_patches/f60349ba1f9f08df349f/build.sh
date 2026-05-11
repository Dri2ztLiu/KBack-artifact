#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/infiniband/core/device.o
