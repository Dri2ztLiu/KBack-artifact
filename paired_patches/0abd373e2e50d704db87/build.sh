#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/vhost/iotlb.o drivers/vhost/vhost.o
