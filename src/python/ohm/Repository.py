#!/usr/bin/env python2.6
#
# [The "New BSD" license]
# Copyright (c) 2011 The Board of Trustees of The University of Alabama
# All rights reserved.
#
# See LICENSE for details.

from __future__ import print_function

__author__  = 'Christopher S. Corley <cscorley@crimson.ua.edu>'
__version__ = '$Id$'

import re
import sys
import os
from shutil import rmtree

from snippets import _make_dir
from Patch import Patch
import pysvn


class Repository:
    def __init__(self, project, starting_revision=-1, ending_revision=-1,
            username='guest', password=''):
        self.client = pysvn.Client()
        self.client.exception_style = 1  # allows retrieval of code/message
        self.client.callback_get_login = self._callback_get_login

        self.project = project
        self.name = self.project.name
        self.url = self.project.url
        self.username = username
        self.password = password
        self.count = 0

        # Regex strings for diff files in this repository
        self.old_file_regex = re.compile('--- ([-/._\w ]+)\t\(revision (\d+)\)')
        self.new_file_regex = re.compile('\+\+\+ ([-/._\w ]+)\t(?:\([\s\S]*\)\t)?\(revision (\d+)\)')
        self.chunk_regex = re.compile('@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')

        if starting_revision < 0:
            self.revStart = pysvn.Revision(pysvn.opt_revision_kind.number,
                    0)
            self.revEnd = pysvn.Revision(pysvn.opt_revision_kind.head)
            revlog = self.client.log(self.url, self.revStart, self.revEnd,
                    limit=1)

            if len(revlog) > 0:
                self.revStart = revlog[0].revision
        else:
            self.revStart = pysvn.Revision(pysvn.opt_revision_kind.number,
                    starting_revision)

        # get the head revision number
        if ending_revision < 0:
            self.revEnd = pysvn.Revision(pysvn.opt_revision_kind.head)
            revlog = self.client.log(self.url, self.revEnd, self.revEnd)

            if len(revlog) > 0:
                self.revEnd = revlog[0].revision
            else:
                self.revEnd = self.client.info2(self.url, recurse=False)[0][1].last_changed_rev
        else:
            self.revEnd = pysvn.Revision(pysvn.opt_revision_kind.number,
                    ending_revision)

        revlog = self.client.log(self.url, self.revStart, self.revEnd)
        self.revList = []

        for log_entry in revlog:
            try:
                log_entry.author
                self.revList.append(log_entry.revision)
            except AttributeError:
                pass
        # going to use the list like a stack, so reverse it so the first
        # revision is the lowest
        self.revList.reverse()

        # after init, please use _moveNextRevision to change these
        self.revCurr = None

        self.total_revs = len(self.revList)

    def __str__(self):
        return '%s %s %s %s' % (self.url, self.revStart.number,
                self.revEnd.number, len(self.revList))

    def __repr__(self):
        return str(self)

    def _callback_get_login(realm, username, save):
        return True, self.username, self.password, False

    def _callback_get_login(self, realm, username, save):
        return True, self.username, self.password, False

    # this function is to be use to cycle the revision objects
    def _moveNextRevision(self):
        if len(self.revList) > 0:
            self.count += 1
            self.revPrev = self.revCurr
            self.revCurr = self.revList.pop()
            if self.revPrev is None:
                self.revPrev = pysvn.Revision(pysvn.opt_revision_kind.number,
                        self.revCurr.number - 1)

    def get_lexer(self, revision_number, file_ext):
        if file_ext not in self.project.lexers:
            return None

        # later:
        # store current lexer in self; then retrieve
        # change lexer when certain revision has been seen?
        # -- wont work for old revisions of files.

        # SVN specific, git will not be so easy.
        lexers = sorted(self.project.lexers[file_ext], key=lambda l: l[0],
                reverse=True)

        # lexer list is now in descending order, so we can just return on
        # first lexer revision number is greater than
        for lexer in lexers:
            if revision_number > lexer[0]:
                return lexer[1]


    def get_parser(self, revision_number, file_ext):
        if file_ext not in self.project.parsers:
            return None

        # SVN specific, git will not be so easy.
        parsers = sorted(self.project.parsers[file_ext], key=lambda p: p[0],
                reverse=True)

        for parser in parsers:
            if revision_number > parser[0]:
                return parser[1]

    # warning
    def checkout(self, fileName, revision_number, try_count=0):
        try_count += 1
        rev = pysvn.Revision(pysvn.opt_revision_kind.number, revision_number)

        if self.url.endswith('/'):
            self.url = self.url[:-1]

        if not fileName.startswith('/'):
            fileName = '/' + fileName

        output = '/tmp/ohm/'+ self.name + '-svn' + fileName
        _make_dir(output[:output.rfind('/')])

        try:
            self.client.export(self.url + fileName, output, revision=rev,
                recurse=False)
        except pysvn.ClientError as e:
            for message, code in e.args[1]:
                if code == 175002:
                    # could not get file, possibly a connection error. keep
                    # trying.
                    if try_count < 5:
                        print('Retry #', try_count, ': ', fileName)
                        return self.checkout(fileName, revision_number, try_count)
                    else:
                        print('Failure 175002')
                        print('Code:', code, 'Message:', message)
                else:
                    print('Code:', code, 'Message:', message, '\n', fileName,
                            revision_number)

        return output


    def getRevisions(self):
        while len(self.revList) > 0:
            self._moveNextRevision()
            try:
                log = self.client.log(self.url, revision_start=self.revCurr,
                        revision_end=self.revCurr, limit=1)
                try:
                    log[0].author
                except (AttributeError, IndexError):
                    print('skipping %d' % self.revCurr.number)
                    continue


                if self.count == 1:
                    # first time trunk appears here...
                    patch_file = self.client.diff('./',
                            url_or_path=self.url.split('trunk/')[0],
                            revision1=self.revPrev,
                            url_or_path2=self.url,
                            revision2=self.revCurr)
                else:
                    patch_file = self.client.diff('./', self.url,
                            revision1=self.revPrev,
                            revision2=self.revCurr)

                patch_lines = patch_file.split('\n')

                if len(log) > 0:
                    log = log[0]
                else:
                    continue

                if os.path.exists('/tmp/ohm/' + self.name + '-svn/'):
                    try:
                        rmtree('/tmp/ohm/' + self.name + '-svn/', True)
                    except OSError:
                        pass

                curr = log.revision.number
                print('Revision %d -- %f complete' % (curr,
                    (float(self.count)/float(self.total_revs))*100))

                # parse for the changes
                patch = Patch(patch_lines, self)

                # Process each diff in the Patch individually for each revision
                # otherwise, we may run into memory troubles for large patches
                for changes in patch.digest():
                    yield log, changes

            except pysvn.ClientError as e:
                for message, code in e.args[1]:
                    if code == 160013 or code == 195012:
                        print('Code:', code, 'Message:', message)
                        print(self.revPrev.number, self.revCurr.number)
                        # does not exist in repository yet
                    else:
                        print('Code:', code, 'Message:', message)
                        print(self.revPrev.number, self.revCurr.number)
