#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/comedi/comedi_fops.o
