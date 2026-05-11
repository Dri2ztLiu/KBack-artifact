#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ipv4/tcp_bpf.o
