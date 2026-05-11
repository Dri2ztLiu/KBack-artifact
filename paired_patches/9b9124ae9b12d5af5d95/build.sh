#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/misc/vmw_vmci/vmci_context.o
