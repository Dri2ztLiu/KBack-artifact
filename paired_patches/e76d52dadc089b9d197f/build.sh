#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/mctp/device.o
