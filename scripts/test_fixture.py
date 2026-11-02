"""Reproducible local media for integration probes; never uses personal recordings."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = 1
FRAMES = 8910
AUDIO_SAMPLES = 14253056


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def ensure_fixture():
    directory = ROOT/'artifacts'/'test-fixtures'/f'v{VERSION}'
    if not directory.resolve().is_relative_to(ROOT):
        raise ValueError('Test fixture directory must remain inside the repository.')
    directory.mkdir(parents=True,exist_ok=True)
    destination = directory/'integration.mkv'
    manifest = directory/'manifest.json'
    if destination.exists() or manifest.exists():
        if not destination.is_file() or not manifest.is_file():
            raise ValueError(f'Incomplete generated fixture: {directory}. Move it aside and rerun.')
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if (data.get('version')!=VERSION or data.get('bytes')!=destination.stat().st_size
                or data.get('sha256')!=sha256(destination)):
            raise ValueError(f'Generated fixture was changed: {directory}. Move it aside and rerun.')
        return destination

    ffmpeg = Path(sys.executable).parent/'Library'/'bin'/'ffmpeg.exe'
    if not ffmpeg.is_file():
        raise FileNotFoundError('Run fixture generation with the project-local Conda Python.')
    print('Generating synthetic integration fixture (297 s, 640x360, stereo PCM)...',flush=True)
    with tempfile.TemporaryDirectory(prefix='generate-',dir=directory) as temporary:
        candidate = Path(temporary)/'integration.mkv'
        command = [str(ffmpeg),'-hide_banner','-v','error','-n',
            '-f','lavfi','-i','testsrc2=size=640x360:rate=30:duration=297',
            '-f','lavfi','-i',
            'aevalsrc=0.18*sin(2*PI*440*t)+0.035*sin(2*PI*997*t)|0.13*sin(2*PI*660*t):s=48000:d=297',
            '-map','0:v:0','-map','1:a:0',
            '-vf',r'setpts=PTS+if(eq(N\,8909)\,3\,0)',
            '-af',f'atrim=end_sample={AUDIO_SAMPLES}',
            '-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',
            '-g','240','-bf','2','-threads','4','-fps_mode','passthrough',
            '-c:a','pcm_s24le',str(candidate)]
        result = subprocess.run(command,capture_output=True,timeout=240)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace'))

        import av
        with av.open(str(candidate)) as container:
            pts = [frame.pts*frame.time_base for frame in container.decode(video=0)]
        with av.open(str(candidate)) as container:
            samples = sum(frame.samples for frame in container.decode(audio=0))
        if (len(pts)!=FRAMES or samples!=AUDIO_SAMPLES or pts[0]!=0
                or not all(a<b for a,b in zip(pts,pts[1:]))
                or not Fraction(13,100)<pts[-1]-pts[-2]<Fraction(14,100)):
            raise ValueError('Generated fixture does not meet its PTS/sample contract.')
        data = {'version':VERSION,'bytes':candidate.stat().st_size,'sha256':sha256(candidate),
                'frames':len(pts),'audio_samples_per_channel':samples,
                'last_video_pts':str(pts[-1]),'last_video_interval':str(pts[-1]-pts[-2]),
                'description':'Synthetic test pattern and stereo tones; not a real-footage benchmark.'}
        candidate_manifest = Path(temporary)/'manifest.json'
        candidate_manifest.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
        # Windows rename refuses existing files, including a racing generator.
        candidate.rename(destination)
        candidate_manifest.rename(manifest)
    print(f'Synthetic fixture ready: {destination.relative_to(ROOT)}',flush=True)
    return destination


if __name__=='__main__':
    print(ensure_fixture())
