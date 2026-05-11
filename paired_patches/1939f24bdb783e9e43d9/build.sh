#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/core/link_watch.o
