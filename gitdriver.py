#!/usr/bin/env python

import os
import sys
import argparse
import mimetypes
import subprocess
import yaml

from drive import GoogleDrive, DRIVE_RW_SCOPE

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--config', '-f', default='gd.conf')
    p.add_argument('--text', '-T', action='append_const', const='text/plain',
            dest='mime_types')
    p.add_argument('--html', '-H', action='append_const', const='text/html',
            dest='mime_types')
    p.add_argument('--mime-type', action='append', dest='mime_types')
    p.add_argument('--raw', '-R', action='append_const', const='raw',
            dest='mime_types', help='Download original document if possible.')
    p.add_argument('docid')

    return p.parse_args()

def download_content_with_mime(gd, mime, rev):
    # mimetypes module randomly decides if `text/plain` is `.c`, `.pl`, or
    # some other source code extension. Let's pin it to `.txt`.
    if mime == 'text/plain':
        file_extension = '.txt'
    # Same for `text/html` - mimetypes can't decide if it's `.htm` or `.html`.
    elif mime == 'text/html':
        file_extension = '.html'
    else:
        file_extension = mimetypes.guess_extension(mime) or ''

    with open('content' + file_extension, 'wb') as fd:
        if 'exportLinks' in rev and (mime != "raw"):
            # If the file provides an 'exportLinks' dictionary,
            # download the requested MIME type.
            r = gd.session.get(rev['exportLinks'][mime])
        elif 'downloadUrl' in rev:
            # Otherwise, if there is a downloadUrl, use that.
            r = gd.session.get(rev['downloadUrl'])
        else:
            raise KeyError('unable to download revision')

        # Write file content into local file.
        for chunk in r.iter_content():
            fd.write(chunk)

    subprocess.call(['git', 'add', 'content' + file_extension])

def commit_revision(gd, opts, rev):
    for mime in opts.mime_types:
        download_content_with_mime(gd, mime, rev);

    env = os.environ.copy()
    env['GIT_COMMITTER_DATE'] = rev['modifiedDate']
    env['GIT_AUTHOR_DATE'] = rev['modifiedDate']
    env['GIT_COMMITTER_NAME'] = rev['lastModifyingUserName']
    env['GIT_AUTHOR_NAME'] = rev['lastModifyingUserName']
    env['GIT_COMMITTER_EMAIL'] = rev['lastModifyingUserName']
    env['GIT_AUTHOR_EMAIL'] = rev['lastModifyingUserName']

    subprocess.call(['git', 'commit', '-m',
        'revision from {0}'.format(rev['modifiedDate'])], env=env)

def main():
    opts = parse_args()
    if not opts.mime_types:
        print('At least one mime-type must be given!')
        exit(1)
    cfg = yaml.load(open(opts.config))
    gd = GoogleDrive(
            client_id=cfg['googledrive']['client id'],
            client_secret=cfg['googledrive']['client secret'],
            scopes=[DRIVE_RW_SCOPE],
            )

    # Establish our credentials.
    gd.authenticate()

    # Get information about the specified file.  This will throw
    # an exception if the file does not exist.
    md = gd.get_file_metadata(opts.docid)

    if os.path.isdir(md['title']):
        # Find revision matching last commit and process only following revisions
        os.chdir(md['title'])
        print('Update repository "{0}"'.format(md['title'].encode('utf-8')))
        last_commit_message = subprocess.check_output('git log -n 1 --format=%B', shell=True).decode(sys.stdout.encoding)
        print('Last commit: ' + last_commit_message + 'Iterating Google Drive revisions:')
        revision_matched = False
        for rev in gd.revisions(opts.docid):
            if revision_matched:
                print('New revision: ' + rev['modifiedDate'])
                commit_revision(gd, opts, rev)
            if rev['modifiedDate'] in last_commit_message:
                print('Found matching revision: ' + rev['modifiedDate'])
                revision_matched = True
        print('Repository is up to date.')
    else:
        # Initialize the git repository.
        print('Create repository "{0}"'.format(md['title'].encode('utf-8')))
        subprocess.call(['git','init',md['title']])
        os.chdir(md['title'])

        # Iterate over the revisions (from oldest to newest).
        for rev in gd.revisions(opts.docid):
            commit_revision(gd, opts, rev)
if __name__ == '__main__':
    main()

