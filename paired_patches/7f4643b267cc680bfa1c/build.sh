#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/hsr/hsr_device.o
