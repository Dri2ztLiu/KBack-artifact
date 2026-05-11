#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/core/dev.o net/packet/af_packet.o
