#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/rose/rose_route.o
