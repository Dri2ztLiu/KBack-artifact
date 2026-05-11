#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/android/binder_alloc.o drivers/android/binder_alloc_selftest.o drivers/android/
