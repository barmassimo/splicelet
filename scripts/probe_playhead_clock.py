"""Playback cursor follows the transport even when video decoding falls behind."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtGui import QGuiApplication,QImage
from splicelet.controller import Preview,FrameProvider
from splicelet.effects import EffectSpan,Fades


class Queue:
    sample_bytes = 8
    def __init__(self): self.frames = []
    def status(self): return len(self.frames),0,False,''
    def take_video(self): return self.frames.pop(0) if self.frames else None


class Sink:
    seconds = 0.
    def processedUSecs(self): return round(self.seconds*1000000)
    def error(self): return type('Error',(),{'value':0})()


app = QGuiApplication([])
preview = Preview(FrameProvider(),muted=True)
preview.timer.stop()
video,audio,sink = preview.video,preview.audio,preview.sink
checks = []
try:
    preview.video = Queue(); preview.audio = Queue(); preview.sink = Sink()
    preview._path = 'synthetic-clock-test'
    preview._duration = 10.
    preview._index = [i/30 for i in range(300)]
    preview._playing = preview._audio_started = True
    preview._has_audio = preview._audio_available = True
    preview._base = 0.
    preview._seek_endpoint = False
    image = QImage(16,9,QImage.Format.Format_RGB888); image.fill(0xff000000)
    positions = []
    # Half-speed video through an overlap, followed by a decoded backlog.
    for clock,stamp in ((1.,1.),(2.,1.5),(3.,2.),(4.,2.5),(5.,5.)):
        preview.sink.seconds = clock
        preview.video.frames.append((preview._generation,stamp,image))
        preview._advance()
        positions.append(preview.position)
        assert abs(preview.position-clock)<1e-6,(clock,stamp,preview.position)
    assert positions==[1.,2.,3.,4.,5.]
    checks.append('audio_clock_cursor_during_slow_video_and_catchup')
    assert 'Frame 151 /' in preview.frameLabel
    preview.sink.seconds = 5.5
    preview._advance()
    assert preview.position==5.5
    assert 'Frame 151 /' in preview.frameLabel
    checks.append('empty_video_queue_advances_cursor_and_retains_displayed_frame_label')
    preview._clips = type('Model',(),{'has_overlaps':False})()
    with patch.object(preview,'effect_spans',return_value=(EffectSpan(4.,8.,Fades(video_in=2.)),)):
        assert preview.videoGain==.5
    preview._clips = None
    checks.append('video_fade_stays_tied_to_displayed_frame')
    preview._has_audio = False
    preview._wall_start = 100.
    with patch('splicelet.controller.time.perf_counter',return_value=106.):
        preview._advance()
    assert preview.position==6.
    checks.append('wall_clock_fallback')
    preview._playing = False
    preview._generation += 1
    preview.video.frames.append((preview._generation,2.,image))
    preview._advance()
    assert preview.position==2. and 'Frame 61 /' in preview.frameLabel
    checks.append('paused_seek_retains_exact_frame_position')
finally:
    preview.video,preview.audio,preview.sink = video,audio,sink
    preview.close()
out = ROOT/'artifacts/playhead-clock-tests'
out.mkdir(parents=True,exist_ok=True)
(out/'report.json').write_text(json.dumps({'checks':checks},indent=2),encoding='utf-8')
print(json.dumps({'passed':len(checks),'checks':checks},indent=2))
