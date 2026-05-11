#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/bonding/bond_main.o
