#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/fuse/acl.o fs/fuse/dir.o fs/fuse/file.o fs/fuse/inode.o fs/fuse/readdir.o fs/fuse/xattr.o fs/fuse/
