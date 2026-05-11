#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bridge/netfilter/ebtables.o
