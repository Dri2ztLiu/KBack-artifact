#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/test-drivers/vidtv/vidtv_bridge.o
