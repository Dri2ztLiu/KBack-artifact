#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/nilfs2/btnode.o fs/nilfs2/btree.o fs/nilfs2/gcinode.o fs/nilfs2/inode.o fs/nilfs2/mdt.o fs/nilfs2/page.o fs/nilfs2/segment.o fs/nilfs2/super.o fs/nilfs2/
