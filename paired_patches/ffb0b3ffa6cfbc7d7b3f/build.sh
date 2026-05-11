#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/i2c/i2c-dev.o
