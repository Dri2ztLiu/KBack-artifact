#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/can/j1939/transport.o
