#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/namei.o
