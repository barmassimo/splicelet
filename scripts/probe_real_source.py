"""Read-only source probes with bounded memory. Outputs only under artifacts/real."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from test_fixture import ensure_fixture
import random
import statistics
import subprocess
import sys
import time
import traceback

import av
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'real'
OUT.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser()
parser.add_argument('source',type=Path,nargs='?',help='Defaults to the generated integration fixture.')
args=parser.parse_args()
SOURCE=(args.source or ensure_fixture()).resolve(strict=True)
FFMPEG=Path(sys.executable).parent/'Library/bin/ffmpeg.exe'
FFPROBE=FFMPEG.with_name('ffprobe.exe')
stat_before=SOURCE.stat()
report={'source':str(SOURCE),'source_bytes':stat_before.st_size,
        'source_kind':'generated synthetic fixture' if args.source is None else 'user-provided media',
        'checks':{},'limitations':[
    'CPU decoding, file-system cache uncontrolled. No UI, GPU display or physical audio/video synchronization test.',
    'Source audio/video end-time differences do not establish lip-sync or clock drift.',
]}


def command(items,timeout=180):
    p=subprocess.run([str(x) for x in items],capture_output=True,timeout=timeout)
    if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace')[-6000:])
    return p.stdout


def ff(*items):
    return command([FFMPEG,'-hide_banner','-v','error','-y',*items])


def save():
    (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


def check(name,fn):
    start=time.perf_counter()
    try:
        result=fn()
        report['checks'][name]={'status':'pass','seconds':time.perf_counter()-start,'result':result}
    except Exception:
        report['checks'][name]={'status':'fail','seconds':time.perf_counter()-start,'error':traceback.format_exc()}
    save()
    print(name,report['checks'][name]['status'],flush=True)


def summary(values):
    ordered=sorted(values)
    return {'median':statistics.median(values),'p95':ordered[int((len(ordered)-1)*.95)],'max':max(values)}


def digest(frame):
    return hashlib.sha256(frame.to_ndarray(format='yuv420p').tobytes()).hexdigest()


def configure(stream):
    stream.thread_type='AUTO'
    stream.codec_context.thread_count=4


def metadata():
    data=json.loads(command([FFPROBE,'-v','error','-show_streams','-show_format','-of','json',SOURCE]))
    report['metadata']=data
    return {s['codec_type']:{k:s.get(k) for k in ('codec_name','width','height','avg_frame_rate','sample_rate','channels','bits_per_sample')} for s in data['streams']}


baseline={}
pts=[]
audio_reference=None
AUDIO_START=59217
AUDIO_END=AUDIO_START+240000
VIDEO_START=37
VIDEO_END=187


def sequential():
    duration=float(report['metadata']['format']['duration'])
    with av.open(str(SOURCE)) as c:
        stream=c.streams.video[0]
        expected=int(duration*float(stream.average_rate))
        rng=random.Random(20261030)
        selected={0,1,37,89,90,expected-2,expected-1}
        selected.update(rng.randrange(expected) for _ in range(33))
        selected.update(range(VIDEO_START,VIDEO_END))
        configure(stream)
        start=time.perf_counter()
        last=start
        costs=[]
        keys=[]
        for index,frame in enumerate(c.decode(stream)):
            now=time.perf_counter()
            costs.append((now-last)*1000)
            pts.append(frame.pts)
            if frame.key_frame: keys.append(index)
            if index in selected: baseline[index]=digest(frame)
            last=time.perf_counter()
            if index and index%1500==0: print(f'decoded {index} frames',flush=True)
        elapsed=time.perf_counter()-start
        # Duration * average_rate is only an estimate (gaps may exist).
        # Always retain the actual final frame as a seek reference.
        baseline[len(pts)-1]=digest(frame)
        report['seek_targets']=sorted(i for i in selected if i< len(pts) and not VIDEO_START<=i<VIDEO_END)
        # Keep exactly 40 reproducible requests, including inside the cut range.
        request_rng=random.Random(42)
        spread=[i for i in sorted(baseline) if not VIDEO_START<=i<VIDEO_END]
        requests=[0,1,37,len(pts)-1]+[request_rng.choice(spread) for _ in range(36)]
        report['seek_targets']=requests
        intervals=Counter(b-a for a,b in zip(pts,pts[1:]))
        assert all(b>a for a,b in zip(pts,pts[1:])), 'Non-monotonic presentation timestamps'
        gaps=[b-a for a,b in zip(keys,keys[1:])]
        nominal=1/stream.average_rate
        timestamp_gaps=[{'after_frame_index':i,'from_seconds':float(a*stream.time_base),
                         'to_seconds':float(b*stream.time_base),'interval_ms':float((b-a)*stream.time_base)*1000}
                        for i,(a,b) in enumerate(zip(pts,pts[1:])) if (b-a)*stream.time_base>nominal*Fraction(3,2)]
        return {'frames':len(pts),'elapsed_seconds':elapsed,'effective_fps_including_selected_hashes':len(pts)/elapsed,
                'decode_wait_ms_excluding_hashes':summary(costs),'timestamp_intervals_ticks':dict(intervals),
                'time_base':str(stream.time_base),'keyframes':len(keys),'max_keyframe_gap_frames':max(gaps,default=0),
                'threads':4,'thread_type':'AUTO','first_video_time':str(pts[0]*stream.time_base),
                'timestamp_gaps':timestamp_gaps,
                'last_video_time':str(pts[-1]*stream.time_base)}


def seeking():
    durations=[]
    presentation=[]
    counts=[]
    detail=[]
    with av.open(str(SOURCE)) as c:
        stream=c.streams.video[0]
        configure(stream)
        for index in report['seek_targets']:
            start=time.perf_counter()
            c.seek(pts[index],stream=stream,backward=True,any_frame=False)
            count=0
            for frame in c.decode(stream):
                count+=1
                if frame.pts>=pts[index]:
                    decoded=time.perf_counter()
                    assert frame.pts==pts[index], (index,frame.pts,pts[index])
                    assert digest(frame)==baseline[index], f'Pixel mismatch at {index}'
                    # A CPU RGB conversion approximates a conventional upload path,
                    # not GPU presentation. Bound to one frame at a time.
                    rgb_start=time.perf_counter()
                    frame.to_ndarray(format='rgb24')
                    presentation.append((time.perf_counter()-rgb_start)*1000)
                    durations.append((decoded-start)*1000)
                    counts.append(count)
                    detail.append({'index':index,'pts':pts[index],'decode_ms':durations[-1],'decoded_frames':count})
                    break
            else: raise AssertionError(f'No frame found at {index}')
    return {'verified_requests':len(detail),'seek_decode_ms':summary(durations),'rgb_conversion_ms':summary(presentation),
            'max_frames_decoded':max(counts),'requests':detail}


def audio():
    global audio_reference
    chunks=[]
    total=0
    errors=[]
    with av.open(str(SOURCE)) as c:
        stream=c.streams.audio[0]
        rate=stream.codec_context.sample_rate
        first=None
        for frame in c.decode(stream):
            actual=Fraction(frame.pts)*frame.time_base
            if first is None: first=actual
            errors.append(float(actual-first-Fraction(total,rate))*1000)
            a=max(AUDIO_START,total)
            b=min(AUDIO_END,total+frame.samples)
            if a<b:
                samples=frame.to_ndarray()
                if frame.format.is_planar: samples=samples.T
                else: samples=samples.reshape(-1,len(frame.layout.channels))
                chunks.append(samples[a-total:b-total].copy())
            total+=frame.samples
        audio_reference=np.concatenate(chunks)
        assert len(audio_reference)==AUDIO_END-AUDIO_START
        video=report['checks']['sequential_decode']['result']
        video_end=float(Fraction(video['last_video_time'])+1/Fraction(report['metadata']['streams'][0]['avg_frame_rate']))
        return {'sample_rate':rate,'samples_per_channel':total,'first_time':str(first),'duration_from_samples_seconds':total/rate,
                'max_abs_timestamp_residual_ms':max(abs(x) for x in errors),
                'video_end_minus_audio_end_ms':(video_end-float(first)-total/rate)*1000,
                'note':'Timestamp residual uses decoded sample count; does not measure physical or perceptual A/V sync.'}


def exact_cut():
    target=OUT/'cut-reference.mkv'
    ff('-i',SOURCE,'-filter_complex',
       f'[0:v:0]trim=start_frame={VIDEO_START}:end_frame={VIDEO_END},setpts=PTS-STARTPTS[v];[0:a:0]atrim=start_sample={AUDIO_START}:end_sample={AUDIO_END},asetpts=PTS-STARTPTS[a]',
       '-map','[v]','-map','[a]','-c:v','ffv1','-level','3','-threads','4','-c:a','pcm_s24le',target)
    with av.open(str(target)) as c:
        decoded=[digest(f) for f in c.decode(video=0)]
    assert decoded==[baseline[i] for i in range(VIDEO_START,VIDEO_END)],'Cut video hashes differ'
    with av.open(str(target)) as c:
        chunks=[]
        for frame in c.decode(audio=0):
            values=frame.to_ndarray()
            chunks.append(values.T if frame.format.is_planar else values.reshape(-1,len(frame.layout.channels)))
        actual=np.concatenate(chunks)
    assert np.array_equal(actual,audio_reference),'Cut audio sample values differ'
    start=time.perf_counter()
    ff('-i',target,'-c:v','libx264','-preset','veryfast','-crf','18','-threads','4','-c:a','aac','-b:a','192k','-movflags','+faststart',OUT/'cut.mp4')
    elapsed=time.perf_counter()-start
    with av.open(str(OUT/'cut.mp4')) as c:
        frames=sum(1 for _ in c.decode(video=0))
    assert frames==VIDEO_END-VIDEO_START
    return {'exact_video_frames':len(decoded),'exact_audio_samples_per_channel':len(actual),'audio_sample_dtype':str(actual.dtype),
            'mp4_frames':frames,'mp4_export_seconds':elapsed,'mp4_bytes':(OUT/'cut.mp4').stat().st_size}


def proxy():
    # Same 15-second source window; short GOP at half resolution.
    start=time.perf_counter()
    proxy_width=max(2,int(report['metadata']['streams'][0]['width'])//4*2)
    ff('-ss','120','-i',SOURCE,'-t','15','-map','0:v:0','-vf',f'scale={proxy_width}:-2','-c:v','libx264','-preset','veryfast','-crf','20','-g','15','-bf','0','-threads','4','-an',OUT/'proxy-15s.mp4')
    encode_seconds=time.perf_counter()-start
    times=[]
    requests=[Fraction(i,10) for i in (1,7,15,29,45,61,79,95,111,139)]
    for path,offset in ((SOURCE,Fraction(120)),(OUT/'proxy-15s.mp4',Fraction(0))):
        values=[]
        with av.open(str(path)) as c:
            stream=c.streams.video[0]
            configure(stream)
            for point in requests:
                target=int((point+offset)/stream.time_base)
                begin=time.perf_counter()
                c.seek(target,stream=stream,backward=True,any_frame=False)
                for f in c.decode(stream):
                    if f.pts>=target:
                        f.to_ndarray(format='rgb24')
                        values.append((time.perf_counter()-begin)*1000)
                        break
                else: raise AssertionError('Proxy comparison seek failed')
        times.append(summary(values))
    return {'window_start_seconds':120,'window_duration_seconds':15,'proxy_width':proxy_width,'proxy_gop_frames':15,
            'proxy_generation_seconds':encode_seconds,'proxy_bytes':(OUT/'proxy-15s.mp4').stat().st_size,
            'original_seek_with_rgb_ms':times[0],'proxy_seek_with_rgb_ms':times[1],
            'note':'Different resolution and GOP; compares editing proxy latency, not equivalent pixel fidelity.'}


check('metadata',metadata)
check('sequential_decode',sequential)
check('random_seek',seeking)
check('audio_timestamps_and_samples',audio)
check('exact_cut_and_export',exact_cut)
check('short_proxy_comparison',proxy)
after=SOURCE.stat()
report['source_size_and_mtime_unchanged']=(stat_before.st_size,stat_before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
save()
sys.exit(any(c['status']=='fail' for c in report['checks'].values()) or not report['source_size_and_mtime_unchanged'])
