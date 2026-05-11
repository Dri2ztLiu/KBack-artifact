#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/ptp/ptp_sysfs.o drivers/ptp/
