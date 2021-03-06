#!/usr/bin/env python2.6
#
# [The "New BSD" license]
# Copyright (c) 2012 The Board of Trustees of The University of Alabama
# All rights reserved.
#
# See LICENSE for details.

from __future__ import print_function

import os


# order preserving uniq for lists
def _uniq(L):
    seen = {}
    result = []
    for item in L:
        if item in seen:
            continue
        seen[item] = 1
        result.append(item)
    return result


# exception handling mkdir -p
def _make_dir(dir):
    try:
        os.makedirs(dir)
    except os.error as e:
        if 17 == e.errno:
            # the directory already exists
            pass
        else:
            print('Failed to create "%s" directory!' % dir)
            sys.exit(e.errno)


# file line length
def _file_len(fname):
    with open(fname) as f:
        for i, l in enumerate(f):
            pass
    return i + 1

def short(sha):
    if sha is not None and type(sha) == str and len(sha) > 7:
        return sha[:7]
    else:
        return sha

