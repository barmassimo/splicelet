"""Repeatable synthetic checks. No network, no original user source modified."""
from __future__ import annotations

import argparse
import array
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import traceback
import wave
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts'
OUT.mkdir(exist_ok=True)
REPORT = {'python': sys.version, 'checks': {}, 'limitations': [
    'Synthetic short 640x360 source; these are correctness probes, not a real-footage performance benchmark.',
    'No validation of GPU zero-copy, perceptual lip-sync, live audio hardware latency or packaged distribution.',
]}


def run(args, timeout=120):
    p = subprocess.run([str(x) for x in args], capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{args}\n{p.stderr.decode(errors="replace")[-6000:]}')
    return p.stdout


def check(name, fn):
    start = time.perf_counter()
    try:
        result = fn()
        REPORT['checks'][name] = {'status': 'pass', 'seconds': time.perf_counter()-start, 'result': result}
    except Exception:
        REPORT['checks'][name] = {'status': 'fail', 'seconds': time.perf_counter()-start, 'error': traceback.format_exc()}
    print(name, REPORT['checks'][name]['status'], flush=True)
    (OUT / 'report.json').write_text(json.dumps(REPORT, indent=2), encoding='utf-8')


def wav_samples(path):
    with wave.open(str(path), 'rb') as f:
        assert (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (2, 2, 48000)
        n = f.getnframes()
        data = array.array('h', f.readframes(n))
    return data, n


def make_audio():
    # Deterministic, distinct stereo samples and periodic impulses.
    data = array.array('h')
    state = 12345
    for i in range(12 * 48000):
        state = (1664525 * state + 1013904223) & 0xffffffff
        left = ((state >> 16) % 12001) - 6000
        right = ((i * 73) % 10001) - 5000
        if i % 48000 == 0:
            left, right = 24000, -24000
        data.extend((left, right))
    with wave.open(str(OUT / 'reference.wav'), 'wb') as f:
        f.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
        f.writeframes(data.tobytes())
    return {'samples_per_channel': 576000, 'sample_rate': 48000}


def ff(*args):
    return run([ARGS.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *args])


def make_video(vfr=False):
    name = 'vfr' if vfr else 'cfr'
    args = ['-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30:duration=12', '-i', OUT/'reference.wav']
    if vfr:
        args += ['-vf', r'select=if(lt(t\,4)\,not(mod(n\,2))\,1)', '-fps_mode', 'vfr']
    args += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-g', '90', '-bf', '3', '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le', OUT/f'{name}.mkv']
    ff(*args)
    meta = json.loads(run([ARGS.ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', OUT/f'{name}.mkv']))
    (OUT/f'{name}-metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    return {'file': f'{name}.mkv', 'streams': [{k:s.get(k) for k in ('codec_name','time_base','r_frame_rate','avg_frame_rate')} for s in meta['streams']]}


def hashes(path, vf=None):
    args = ['-i', path, '-map', '0:v:0']
    if vf:
        args += ['-vf', vf]
    text = ff(*args, '-fps_mode', 'passthrough', '-f', 'framemd5', '-').decode()
    return [line.split(',')[-1].strip() for line in text.splitlines() if line and not line.startswith('#')]


def export_cut():
    ff('-i', OUT/'cfr.mkv', '-filter_complex',
       '[0:v]trim=start_frame=37:end_frame=187,setpts=PTS-STARTPTS[v];[0:a]atrim=start_sample=59217:end_sample=299217,asetpts=PTS-STARTPTS[a]',
       '-map', '[v]', '-map', '[a]', '-c:v', 'ffv1', '-c:a', 'pcm_s16le', OUT/'cut-reference.mkv')
    original = hashes(OUT/'cfr.mkv')
    cut = hashes(OUT/'cut-reference.mkv')
    assert cut == original[37:187], 'Video frame identity mismatch'
    ff('-i', OUT/'cut-reference.mkv', '-map', '0:a:0', '-c:a', 'pcm_s16le', OUT/'cut-reference.wav')
    original_audio, _ = wav_samples(OUT/'reference.wav')
    cut_audio, n = wav_samples(OUT/'cut-reference.wav')
    assert cut_audio == original_audio[59217*2:299217*2], 'Audio sample identity mismatch'
    ff('-i', OUT/'cut-reference.mkv', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', OUT/'cut.mp4')
    meta = json.loads(run([ARGS.ffprobe, '-v', 'error', '-count_frames', '-show_streams', '-of', 'json', OUT/'cut.mp4']))
    video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
    assert int(video['nb_read_frames']) == 150
    # The MP4 is lossy: compare decoded frame quality against the exact reference.
    # Compare by frame index: Matroska has millisecond timestamps whereas MP4
    # has a different time base. Default framesync would compare wrong pairs.
    p = subprocess.run([str(ARGS.ffmpeg), '-hide_banner', '-i', str(OUT/'cut.mp4'), '-i', str(OUT/'cut-reference.mkv'), '-filter_complex', '[0:v]settb=1/30,setpts=N[a];[1:v]settb=1/30,setpts=N[b];[a][b]psnr=stats_file=mp4-psnr.log', '-an', '-f', 'null', '-'], cwd=OUT, capture_output=True, timeout=120)
    assert p.returncode == 0, p.stderr.decode(errors='replace')
    psnr_log = (OUT/'mp4-psnr.log').read_text()
    psnr = [float(line.split('psnr_avg:')[1].split()[0]) for line in psnr_log.splitlines()]
    assert len(psnr) == 150 and min(psnr) > 30, 'Export differs excessively from expected decoded frames'
    return {'video_frames_identical_before_lossy_encoding': len(cut), 'audio_samples_bit_exact_per_channel': n,
            'audio_cut_start_sample': 59217, 'audio_cut_start_seconds': str(Fraction(59217,48000)),
            'mp4_video_frames': 150, 'mp4_min_frame_psnr_db': min(psnr),
            'note': 'AAC sample values are lossy; exact sample checks apply to the PCM reference.'}


def crossfade():
    ff('-i', OUT/'reference.wav', '-filter_complex',
       '[0:a]asplit=2[a][b];[a]atrim=start_sample=0:end_sample=192000,asetpts=PTS-STARTPTS[x];[b]atrim=start_sample=240000:end_sample=432000,asetpts=PTS-STARTPTS[y];[x][y]acrossfade=ns=12000:c1=tri:c2=tri[z]',
       '-map', '[z]', '-c:a', 'pcm_s16le', OUT/'crossfade.wav')
    data, _ = wav_samples(OUT/'reference.wav')
    actual, n = wav_samples(OUT/'crossfade.wav')
    assert n == 372000, n
    assert actual[:180000*2] == data[:180000*2]
    assert actual[192000*2:] == data[252000*2:432000*2]
    errors = []
    for i in range(12000):
        for ch in (0,1):
            expected = data[(180000+i)*2+ch] * ((11999-i)/12000) + data[(240000+i)*2+ch] * (i/12000)
            errors.append(abs(actual[(180000+i)*2+ch] - expected))
    assert max(errors) <= 3, max(errors)
    return {'samples_per_channel': n, 'overlap_samples': 12000, 'max_linear_mix_error_int16_units': max(errors)}


def pyav_seek():
    import av
    result = {}
    for kind in ('cfr','vfr'):
        path = OUT/f'{kind}.mkv'
        with av.open(str(path)) as c:
            baseline = [(f.pts, hashlib.sha256(f.to_ndarray(format='rgb24').tobytes()).hexdigest()) for f in c.decode(video=0)]
        intervals = sorted(set(baseline[i+1][0]-baseline[i][0] for i in range(len(baseline)-1)))
        if kind == 'vfr':
            assert max(intervals) > min(intervals)*1.5, intervals
        rng = random.Random(42)
        targets = [0,1,36,37,89,90,len(baseline)-1]+[rng.randrange(len(baseline)) for _ in range(33)]
        timings=[]
        decoded_counts=[]
        with av.open(str(path)) as c:
            stream=c.streams.video[0]
            for index in targets:
                target_pts, expected_hash = baseline[index]
                start=time.perf_counter()
                c.seek(target_pts, stream=stream, backward=True, any_frame=False)
                count=0
                for f in c.decode(stream):
                    count+=1
                    if f.pts >= target_pts:
                        assert f.pts == target_pts, (kind,index,f.pts,target_pts)
                        actual_hash=hashlib.sha256(f.to_ndarray(format='rgb24').tobytes()).hexdigest()
                        assert actual_hash == expected_hash, (kind,index)
                        break
                else:
                    raise AssertionError(f'No frame at {kind}:{index}')
                timings.append((time.perf_counter()-start)*1000)
                decoded_counts.append(count)
        result[kind]={'frames':len(baseline),'seeks_verified':len(targets),'median_seek_ms':statistics.median(timings),
                      'p95_seek_ms':sorted(timings)[int((len(timings)-1)*.95)],'max_seek_ms':max(timings),
                      'max_frames_decoded_for_seek':max(decoded_counts),'pts_intervals':intervals}
    return result


def video_crossfade():
    ff('-f','lavfi','-i','color=black:size=64x64:rate=30:duration=2',
       '-f','lavfi','-i','color=white:size=64x64:rate=30:duration=2',
       '-filter_complex','[0:v]format=yuv444p[a];[1:v]format=yuv444p[b];[a][b]xfade=transition=fade:duration=0.5:offset=1.5[v]',
       '-map','[v]','-c:v','ffv1',OUT/'video-crossfade.mkv')
    raw=ff('-i',OUT/'video-crossfade.mkv','-pix_fmt','yuv444p','-f','rawvideo','-')
    frame_bytes=64*64*3
    assert len(raw)%frame_bytes==0
    values=[raw[i] for i in range(0,len(raw),frame_bytes)]
    assert len(values)==105, len(values)
    assert all(v==16 for v in values[:45])
    assert all(v==235 for v in values[60:])
    errors=[abs(values[i]-(16+219*(i-45)/15)) for i in range(45,60)]
    assert max(errors)<=2, (values[45:61],max(errors))
    return {'frames':len(values),'overlap_frames':15,'max_luma_error':max(errors),'transition_luma':values[45:61]}


def cancellation():
    # Real-time input ensures this doesn't finish before cancellation.
    command=[str(ARGS.ffmpeg),'-hide_banner','-loglevel','error','-re','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-t','120','-f','null','-']
    p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        time.sleep(.6)
        assert p.poll() is None
        start=time.perf_counter()
        _,err=p.communicate(b'q\n',timeout=5)
        assert p.returncode == 0, err.decode(errors='replace')
        return {'graceful_stop_ms':(time.perf_counter()-start)*1000,'returncode':p.returncode}
    finally:
        if p.poll() is None:
            p.kill()
            p.communicate()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--ffprobe',default='ffprobe')
    parser.add_argument('--skip-pyav',action='store_true')
    ARGS=parser.parse_args()
    REPORT['ffmpeg']=run([ARGS.ffmpeg,'-version']).decode().splitlines()[0]
    for pkg in ('av','PySide6','numpy'):
        try: REPORT[pkg]=importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError: REPORT[pkg]=None
    check('generate_audio',make_audio)
    check('generate_cfr',lambda:make_video(False))
    check('generate_vfr',lambda:make_video(True))
    check('exact_cut_and_mp4',export_cut)
    check('audio_crossfade',crossfade)
    check('video_crossfade',video_crossfade)
    check('export_cancellation',cancellation)
    if not ARGS.skip_pyav:
        check('pyav_seek',pyav_seek)
    sys.exit(any(c['status']=='fail' for c in REPORT['checks'].values()))
