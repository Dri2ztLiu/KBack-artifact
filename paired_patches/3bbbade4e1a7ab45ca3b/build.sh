#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/hwmon/corsair-cpro.o
