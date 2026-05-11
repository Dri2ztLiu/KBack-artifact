#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/l2tp/l2tp_ip6.o
