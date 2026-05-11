#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/iommu/iommufd/iova_bitmap.o
