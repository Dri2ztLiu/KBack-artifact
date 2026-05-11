#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/packet/af_packet.o
