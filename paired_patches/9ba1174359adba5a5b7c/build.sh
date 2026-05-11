#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bridge/br.o net/bridge/br_fdb.o net/bridge/
