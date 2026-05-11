#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/ppp/pppoe.o
