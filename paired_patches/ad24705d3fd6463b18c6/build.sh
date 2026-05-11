#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/netdevsim/bpf.o
