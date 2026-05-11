#!/bin/sh
set -e
make allyesconfig
make -j `nproc` lib/debugobjects.o
