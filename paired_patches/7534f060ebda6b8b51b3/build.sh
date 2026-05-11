#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/acpi/nfit/core.o
