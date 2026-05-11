#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/char/ttyprintk.o
