#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/atm/atmtcp.o
