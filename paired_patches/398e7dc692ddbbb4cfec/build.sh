#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/phy/mdio_bus.o
