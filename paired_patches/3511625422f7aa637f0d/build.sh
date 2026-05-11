#!/bin/sh
set -e
make allyesconfig
make -j `nproc` mm/mempolicy.o
