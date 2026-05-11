#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/mc/mc-devnode.o
