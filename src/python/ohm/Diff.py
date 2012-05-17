#!/USR/BIn/env python2.6
#
# [The "New BSD" license]
# Copyright (c) 2010,2011 The Board of Trustees of The University of Alabama
# All rights reserved.
#
# See LICENSE for details.

from __future__ import with_statement
from __future__ import print_function

__author__  = 'Christopher S. Corley <cscorley@crimson.ua.edu>'
__version__ = '$Id$'

import os
import sys
import codecs
from difflib import SequenceMatcher
from datetime import datetime
from pprint import pprint

from Chunk import Chunk
from File import File
from antlr3 import ANTLRFileStream, ANTLRInputStream, CommonTokenStream

from snippets import _make_dir, _uniq, _file_len
import pysvn


class Diff:
    def __init__(self, project_repo):
        self.project_repo = project_repo

        self.scp = []

        self.old_source = None
        self.new_source = None
        self.old_file = None
        self.new_file = None
        self.digestion = None

    def _get_parser_results(self, file_path, source, revision_number):
        ext = os.path.splitext(file_path)[1]

        SourceLexer = self.project_repo.get_lexer(revision_number, ext)
        if SourceLexer is None:
            return None

        # Run ANTLR on the original source and build a list of the methods
        try:
            lexer = SourceLexer(ANTLRFileStream(file_path, 'latin-1'))
        except ValueError:
            lexer = SourceLexer(ANTLRFileStream(file_path, 'utf-8'))
        except IOError:
            return None

        SourceParser = self.project_repo.get_parser(revision_number, ext)
        if SourceParser is None:
            return None

        parser = SourceParser(CommonTokenStream(lexer))
        parser.file_name = source
        parser.file_len = _file_len(file_path)
        return parser.compilationUnit()

    def digest(self, diff_file):
        regex = self.project_repo.diff_regex

        self.scp = []

        diff_divisions = []
        self.old_source = None
        self.new_source = None
        self.old_source_text = None
        self.new_source_text = None
        if len(diff_file) == 0:
            return None

        self.old_file = None
        self.new_file = None
        self.digestion = None

        log = []

        temp = []
        start = 0
        old_revision_number = 0
        new_revision_number = 0
        list_itr = None

        isNewFile = False
        isRemovedFile = False

        while start < len(diff_file) and not regex.chunk.match(diff_file[start]):
            m = regex.old_file.match(diff_file[start])
            if m:
                self.old_source = m.group(1)
                old_revision_number = int(m.group(2))

                nm = regex.new_file.match(diff_file[start + 1])
                if nm:
                    self.new_source = nm.group(1)
                    new_revision_number = int(nm.group(2))

                if (old_revision_number == 0):
                    isNewFile = True

                start += 1
                break
            start += 1

        # catch diffs that are for only property changes
        if self.old_source is None and self.new_source is None:
            return None

        # Divide the diff into separate chunks
        for i in range(start + 1, len(diff_file)):
            tmp = diff_file[i]
            chunk_matcher = regex.chunk.match(tmp)
            if chunk_matcher:
                if len(diff_divisions) == 0:
                    if int(chunk_matcher.group(1)) == 0 and int(chunk_matcher.group(2)) == 0:
                        if not isNewFile:
                            print('Uhh.... captain? New file not new?',
                                    self.old_source, old_revision_number,
                                    self.new_source, new_revision_number)
                        isNewFile = True
                    elif int(chunk_matcher.group(3)) == 0 and int(chunk_matcher.group(4)) == 0:
                        isRemovedFile = True
                for j in range(start, i - 1):
                    temp.append(diff_file[j])
                if len(temp) > 0:
                    diff_divisions.append(temp)
                temp = []
                start = i

        for j in range(start, len(diff_file)):
            temp.append(diff_file[j])
        diff_divisions.append(temp)

        self.PLD = Chunk(diff_divisions)

        if old_revision_number == 0:
            isNewFile = True
        if new_revision_number == 0:
            isRemovedFile = True

        # Begin prep to run ANTLR on the source files

        # Check out from SVN the original file
        if not isNewFile:
            file_path = self.project_repo.get_file(self.old_source, old_revision_number)
            res = self._get_parser_results(file_path, self.old_source, old_revision_number)
            if res is None:
                # some error has occured.
                return None
            self.old_file = res[0]
            log = res[1]
            with open(file_path, 'r') as f:
                self.old_source_text = f.readlines()

            self.old_file.text = self.old_source_text
            self.PLD.digest_old(self.old_file)
            #self.old_file.recursive_print()

        if not isRemovedFile:
            file_path = self.project_repo.get_file(self.new_source, new_revision_number)
            res = self._get_parser_results(file_path, self.new_source, new_revision_number)
            if res is None:
                # some error has occured.
                return None
            self.new_file = res[0]
            log = res[1]

            with open(file_path, 'r') as f:
                self.new_source_text = f.readlines()

            self.new_file.text = self.new_source_text
            self.PLD.digest_new(self.new_file)
            #self.new_file.recursive_print()



        self.recursive_scp(self.old_file, self.new_file)
        if isNewFile:
            self.digestion = self.new_file
        else:
            self.digestion = self.old_file

        if not isRemovedFile and not isNewFile:
            if self.old_file.package_name != self.new_file.package_name:
                self.digestion.package_name = self.new_file.package_name

        if not isRemovedFile:
            self.digestion.removed_count += self.new_file.removed_count
            self.digestion.added_count += self.new_file.added_count
            self.recursive_walk(self.digestion, self.new_file)

        # make sure digestion is a list before stopping
        self.digestion = [self.digestion]


    def recursive_walk(self, old, new):
        if old is None or new is None:
            return

        if old.has_sub_blocks or new.has_sub_blocks:
            if old.has_sub_blocks:
                old_set = set(old.sub_blocks)
            else:
                old_set = set()
            if new.has_sub_blocks:
                new_set = set(new.sub_blocks)
            else:
                new_set = set()
        else:
            return

        common_set = old_set & new_set
        added_set = new_set - common_set

        for block in common_set:
            o = old.sub_blocks[old.sub_blocks.index(block)]
            n = new.sub_blocks[new.sub_blocks.index(block)]
            o.removed_count += n.removed_count
            o.added_count += n.added_count

            # prune the unchanged blocks
        #    if o.removed_count == 0 and o.added_count == 0:
        #        old.sub_blocks.remove(o)
        #    else:
            self.recursive_walk(o, n)

        old.sub_blocks.extend(added_set)


    def recursive_scp(self, old, new):
        """ This method is intended to recursively process all sub_blocks in
        the given block"""
        if old is None or new is None:
            return

        if old.has_sub_blocks and new.has_sub_blocks:
            old_set = set(old.sub_blocks)
            new_set = set(new.sub_blocks)
        else:
            return

        common_set = old_set & new_set
        added_set = new_set - common_set
        removed_set = old_set - common_set

        for block in common_set:
            o = old.sub_blocks[old.sub_blocks.index(block)]
            n = new.sub_blocks[new.sub_blocks.index(block)]
            self.recursive_scp(o, n)

        # get scp
        scp = self.digestSCP(removed_set, added_set)
        old.scp = scp

        for pair in scp:
            if pair[0] in old and pair[1] in new:
                o = old.sub_blocks[old.sub_blocks.index(pair[0])]
                n = new.sub_blocks[new.sub_blocks.index(pair[1])]
                self.recursive_scp(o, n)

        self.scp += scp

    def digestSCP(self, removed_set, added_set):
        # renames: yes, merges: no, splits: not handled, clones: yes
        possible_pairs = []
        max_pair = None
        tiebreak_pairs = []
        for r_block in removed_set:
            if max_pair is not None:
                #added_set.remove(max_pair[1]) # do not attempt to re-pair
                max_pair = None

            tiebreak_pairs = []
            for a_block in added_set:
                # for pairing of blocks with a small number of sub_blocks (1-3), this
                # will be fairly inaccurate
                r_block_seq = None
                a_block_seq = None

                if r_block.has_sub_blocks and a_block.has_sub_blocks:
                    if len(r_block.sub_blocks) > 2 and len(a_block.sub_blocks) > 2:
                        r_block_seq = r_block.sub_blocks
                        a_block_seq = a_block.sub_blocks

                if r_block_seq is None or a_block_seq is None:
                    r_block_seq = r_block.text
                    a_block_seq = a_block.text

                s = SequenceMatcher(None, r_block_seq, a_block_seq)
                relation_value = s.ratio()
                if relation_value == 0.0:
                    continue

                if max_pair is None:
                    max_pair = (r_block, a_block, relation_value)
                    tiebreak_pairs = []
                elif relation_value > max_pair[2]:
                    max_pair = (r_block, a_block, relation_value)
                    tiebreak_pairs = []
                elif relation_value == max_pair[2]:
                    # tie breaker needed, compare the names
                    tb = self._tiebreaker(r_block.name, a_block.name,
                            max_pair[1].name)
                    if tb == 0:
                        tb = self._tiebreaker(str(r_block), str(a_block),
                            str(max_pair[1]))

                    if tb == 0:
                        tiebreak_pairs.append((r_block, a_block,
                            relation_value))
                        tiebreak_pairs.append(max_pair)

                    if tb == 1:
                        max_pair = (r_block, a_block, relation_value)

            # since r_block->a_block pair has been found, should we remove
            # a_block from the list of possiblities?
            if max_pair is not None:
                if not max_pair in tiebreak_pairs:
                    possible_pairs.append(max_pair)
            if len(tiebreak_pairs) > 0:
                #possible_pairs.extend(tiebreak_pairs)
                print('------------')
                for each in tiebreak_pairs:
                    print('tiebreaker needed: %s, %s, %s' % each)
                print('------------')

        return self._prunePairs(_uniq(possible_pairs))

    def _prunePairs(self, possible_pairs):
        # find pairs which have duplicates, select only best
        more_possible = []
        tiebreak_pairs = []

        max_pair = None
        for each in possible_pairs:
            tiebreak_pairs = []
            max_pair = each
            for pair in possible_pairs:
                if max_pair != pair and max_pair[0] == pair[0]:
                    if max_pair[2] < pair[2]:
                        max_pair = pair
                        tiebreak_pairs = []
                    elif max_pair[2] == pair[2]:
                        tiebreak_pairs.append(pair)
                        tiebreak_pairs.append(max_pair)

            if not max_pair in tiebreak_pairs:
                more_possible.append(max_pair)
            if len(tiebreak_pairs) > 0:
                #possible_pairs.extend(tiebreak_pairs)
                pass


        tiebreak_pairs = []
        most_possible = []
        for each in more_possible:
            tiebreak_pairs = []
            max_pair = each
            for pair in more_possible:
                if max_pair != pair and max_pair[1] == pair[1]:
                    if max_pair[2] < pair[2]:
                        max_pair = pair
                        tiebreak_pairs = []
                    elif max_pair[2] == pair[2]:
                        tiebreak_pairs.append(pair)
                        tiebreak_pairs.append(max_pair)

            if not max_pair in tiebreak_pairs:
                most_possible.append(max_pair)
            if len(tiebreak_pairs) > 0:
                #possible_pairs.extend(tiebreak_pairs)
                pass


        return _uniq(most_possible)

    def _tiebreaker(self, old, new_a, new_b):
        s = SequenceMatcher(None, new_a, old)
        a_ratio = s.ratio()
        s.set_seq1(new_b)
        b_ratio = s.ratio()
        if a_ratio > b_ratio:
            return 1
        elif a_ratio < b_ratio:
            return 2

        return 0
