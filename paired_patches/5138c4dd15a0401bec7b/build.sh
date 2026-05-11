#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/can/dev/dev.o drivers/net/can/slcan.o drivers/net/can/vcan.o drivers/net/can/vxcan.o net/can/af_can.o net/can/j1939/main.o net/can/j1939/socket.o net/can/proc.o include/linux/ include/linux/can/
