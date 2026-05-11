#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/can/j1939/main.o net/can/j1939/socket.o net/can/j1939/
