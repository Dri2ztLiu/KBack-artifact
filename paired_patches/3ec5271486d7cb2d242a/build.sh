#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/geneve.o
