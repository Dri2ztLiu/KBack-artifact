#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/video/fbdev/core/fbcon.o
