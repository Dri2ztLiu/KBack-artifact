#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/scsi/hosts.o
