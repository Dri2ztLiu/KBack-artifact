#!/bin/sh
set -e
make allyesconfig
make -j `nproc` kernel/pid.o kernel/pid_namespace.o include/linux/
