#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/rc/streamzap.o
