#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/kcm/kcmsock.o include/net/
