#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ipv4/udp.o net/ipv6/udp.o
