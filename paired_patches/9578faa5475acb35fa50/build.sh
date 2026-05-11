#!/bin/sh
set -e
make allyesconfig
make -j `nproc` mm/khugepaged.o include/trace/events/
