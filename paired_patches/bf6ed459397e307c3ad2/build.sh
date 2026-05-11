#!/bin/sh
set -e
make allyesconfig
make -j `nproc` include/net/netfilter/
