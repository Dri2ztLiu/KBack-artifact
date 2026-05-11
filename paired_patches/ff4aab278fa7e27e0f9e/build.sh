#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/nvme/target/configfs.o
