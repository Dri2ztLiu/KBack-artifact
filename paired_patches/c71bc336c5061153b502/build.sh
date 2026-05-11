#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/core/stream.o
