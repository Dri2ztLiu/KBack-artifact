#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/netlabel/netlabel_cipso_v4.o
