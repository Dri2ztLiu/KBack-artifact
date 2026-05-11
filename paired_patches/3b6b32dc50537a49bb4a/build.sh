#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/eventpoll.o include/linux/
