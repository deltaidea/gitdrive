#!/usr/bin/python

import os
import sys
import argparse
import subprocess
import yaml

from drive import GoogleDrive, DRIVE_RW_SCOPE

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--config', '-f', default='gd.conf')
    p.add_argument('--text', '-T', action='store_const', const='text/plain',
            dest='mime_type')
    p.add_argument('--html', '-H', action='store_const', const='text/html',
            dest='mime_type')
    p.add_argument('--mime-type', dest='mime_type')
    p.add_argument('--raw', '-R', action='store_true',
            help='Download original document if possible.')
    p.add_argument('docid')

    return p.parse_args()

def commit_revision(gd, opts, rev):
    with open('content', 'w') as fd:
        if 'exportLinks' in rev and not opts.raw:
            # If the file provides an 'exportLinks' dictionary,
            # download the requested MIME type.
            r = gd.session.get(rev['exportLinks'][opts.mime_type])
        elif 'downloadUrl' in rev:
            # Otherwise, if there is a downloadUrl, use that.
            r = gd.session.get(rev['downloadUrl'])
        else:
            raise KeyError('unable to download revision')

        # Write file content into local file.
        for chunk in r.iter_content():
            fd.write(chunk)

    # Prepare environment variables to change commit time
    env = os.environ.copy()
    env['GIT_COMMITTER_DATE'] = rev['modifiedDate']
    env['GIT_AUTHOR_DATE'] = rev['modifiedDate']
    env['GIT_COMMITTER_NAME'] = rev['lastModifyingUserName']
    env['GIT_AUTHOR_NAME'] = rev['lastModifyingUserName']
    env['GIT_COMMITTER_EMAIL'] = rev['lastModifyingUserName']
    env['GIT_AUTHOR_EMAIL'] = rev['lastModifyingUserName']

    # Commit changes to repository.
    subprocess.call(['git', 'add', 'content'])
    subprocess.call(['git', 'commit', '-m',
        'revision from %s' % rev['modifiedDate']], env=env)


def main():
    opts = parse_args()
    if not opts.mime_type:
		print "Exactly one mime-type must be given!"
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
        print 'Update repository "%(title)s"' % md
        last_commit_message = subprocess.check_output('git log -n 1 --format=%B', shell=True)
        print 'Last commit: ' + last_commit_message + 'Iterating Google Drive revisions:'
        revision_matched = False
        for rev in gd.revisions(opts.docid):            
            if revision_matched:
                print "New revision: " + rev['modifiedDate']
                commit_revision(gd, opts, rev)
            if rev['modifiedDate'] in last_commit_message:
                print "Found matching revision: " + rev['modifiedDate']
                revision_matched = True
        print "Repository is up to date."
    else:
        # Initialize the git repository.
        print 'Create repository "%(title)s"' % md
        subprocess.call(['git','init',md['title']])
        os.chdir(md['title'])

        # Iterate over the revisions (from oldest to newest).
        for rev in gd.revisions(opts.docid):
            commit_revision(gd, opts, rev)
if __name__ == '__main__':
    main()

