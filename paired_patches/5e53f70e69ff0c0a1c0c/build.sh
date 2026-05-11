#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/autofs/waitq.o
