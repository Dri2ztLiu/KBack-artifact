#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/test-drivers/vimc/vimc-streamer.o
