#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/v4l2-core/v4l2-ioctl.o
