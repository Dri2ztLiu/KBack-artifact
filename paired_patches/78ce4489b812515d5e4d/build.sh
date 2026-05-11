#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/can/af_can.o net/can/proc.o net/can/
