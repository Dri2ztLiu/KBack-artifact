#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/iommu/iommufd/io_pagetable.o
