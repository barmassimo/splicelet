"""Optional Git identity for source runs and frozen build snapshots."""
import json
from pathlib import Path
import re
import subprocess
import sys


def git_build_info(root):
    root = Path(root)
    if not (root/'.git').exists():
        return {}
    def git(*arguments):
        return subprocess.run(
            ['git', '-C', str(root), *arguments], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding='utf-8', errors='replace', timeout=2,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
        ).stdout.strip()
    try:
        commit = git('rev-parse','--verify','HEAD')
        modified = bool(git('status','--porcelain','--untracked-files=normal'))
    except (OSError,subprocess.SubprocessError):
        return {}
    return validated_info({'commit':commit,'modified':modified})


def validated_info(info):
    if (isinstance(info,dict) and
        isinstance(info.get('commit'),str) and
        re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',info['commit']) and
        isinstance(info.get('modified'),bool)):
        return {'commit':info['commit'],'modified':info['modified']}
    return {}


def current_build_info():
    if getattr(sys,'frozen',False):
        # Never inspect the user's current repository from a portable executable.
        try:
            return validated_info(json.loads(Path(__file__).with_name('_build_info.json').read_text(encoding='utf-8')))
        except (OSError,ValueError):
            return {}
    return git_build_info(Path(__file__).resolve().parents[1])


def version_label(version,info):
    info = validated_info(info)
    if not info:
        return version
    state = ', modified' if info['modified'] else ''
    return f"{version} ({info['commit'][:7]}{state})"
