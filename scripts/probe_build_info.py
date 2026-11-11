"""Check optional Git identity, dirty states and portable snapshots without Qt."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from splicelet import __version__
from splicelet import build_info

OUT = ROOT/'artifacts'/'build-info-tests'
OUT.mkdir(parents=True,exist_ok=True)
repo = OUT/uuid4().hex
repo.mkdir()
checks = []


def passed(name):
    checks.append(name)
    print('PASS',name,flush=True)


def git(*arguments):
    return subprocess.run(['git','-C',str(repo),*arguments],check=True,
                          capture_output=True,text=True).stdout.strip()


assert build_info.git_build_info(repo)=={}
assert build_info.version_label(__version__,{})==__version__
passed('source_archive_without_git_metadata')
if shutil.which('git'):
    git('init','--quiet')
    assert build_info.git_build_info(repo)=={}
    passed('repository_without_commits')
    (repo/'source.txt').write_text('original\n',encoding='utf-8')
    git('add','source.txt')
    git('-c','user.name=Build probe','-c','user.email=probe@example.invalid',
        '-c','commit.gpgsign=false','commit','--quiet','-m','Fixture')
    commit = git('rev-parse','HEAD')
    clean = {'commit':commit,'modified':False}
    assert build_info.git_build_info(repo)==clean
    (repo/'source.txt').write_text('changed\n',encoding='utf-8')
    assert build_info.git_build_info(repo)['modified'] is True
    git('add','source.txt')
    assert build_info.git_build_info(repo)['modified'] is True
    git('reset','--hard','--quiet','HEAD')
    (repo/'untracked.txt').write_text('new\n',encoding='utf-8')
    dirty = build_info.git_build_info(repo)
    assert dirty['modified'] is True
    passed('clean_repository_and_unstaged_staged_untracked_changes')
else:
    # Git remains optional even for the maintained suite.
    (repo/'.git').mkdir()
    commit = 'a'*40
    clean = {'commit':commit,'modified':False}
    dirty = {'commit':commit,'modified':True}
    for status,expected in (('',clean),(' M source.txt',dirty)):
        outputs = [subprocess.CompletedProcess([],0,commit),subprocess.CompletedProcess([],0,status)]
        with patch.object(build_info.subprocess,'run',side_effect=outputs):
            assert build_info.git_build_info(repo)==expected
    passed('clean_and_modified_identity_with_simulated_git')
assert build_info.version_label(__version__,clean)==f'{__version__} ({commit[:7]})'
assert build_info.version_label(__version__,dirty)==f'{__version__} ({commit[:7]}, modified)'
with patch.object(build_info.subprocess,'run',side_effect=FileNotFoundError):
    assert build_info.git_build_info(repo)=={}
with patch.object(build_info.subprocess,'run',side_effect=subprocess.TimeoutExpired('git',2)):
    assert build_info.git_build_info(repo)=={}
passed('missing_or_unresponsive_git_fallback')
snapshot = repo/'_build_info.json'
snapshot.write_text(json.dumps(dirty),encoding='utf-8')
with patch.object(sys,'frozen',True,create=True), \
     patch.object(build_info,'__file__',str(repo/'build_info.py')), \
     patch.object(build_info.subprocess,'run',side_effect=AssertionError('Frozen build invoked Git')):
    assert build_info.current_build_info()==dirty
    for invalid in ('{','[]','{"commit":"bad","modified":false}',
                    json.dumps({'commit':commit,'modified':'false'})):
        snapshot.write_text(invalid,encoding='utf-8')
        assert build_info.current_build_info()=={}
    snapshot.unlink()
    assert build_info.current_build_info()=={}
passed('portable_snapshot_without_git_and_invalid_metadata_fallback')
(OUT/'report.json').write_text(json.dumps({'status':'pass','checks':checks},indent=2)+'\n',encoding='utf-8')
