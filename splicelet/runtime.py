"""Locate development and portable runtime files without depending on the cwd."""
from pathlib import Path
import sys


FROZEN = getattr(sys,'frozen',False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT/'artifacts'


def ffmpeg_executable():
    if FROZEN:
        return Path(sys._MEIPASS)/'ffmpeg'/'ffmpeg.exe'
    return Path(sys.executable).parent/'Library'/'bin'/'ffmpeg.exe'
