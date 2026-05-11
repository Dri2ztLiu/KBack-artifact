#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/nsh/nsh.o
