"""Compare the actual preview worker's PCM stream with an independent FFmpeg render."""
import argparse
import json
from pathlib import Path
from test_fixture import ensure_fixture
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from splicelet.source import Decoder,Job,audio_sample_timeline

parser=argparse.ArgumentParser()
parser.add_argument('source',type=Path,nargs='?',help='Defaults to the generated integration fixture.')
args=parser.parse_args()
source=str((args.source or ensure_fixture()).resolve(strict=True))
ffmpeg=Path(sys.executable).parent/'Library/bin/ffmpeg.exe'
timeline=audio_sample_timeline(source)
checks=[]
for fmt,dtype,bps in (('flt','<f4',4),('s16','<i2',2)):
    for start,length in ((0.,3.),(59217/48000,2.),(224.033,3.),(296.9,.2)):
        worker=Decoder('audio',sample_format=fmt,bytes_per_sample=bps)
        worker.request(1,Job(1,source,start,0.,start+length,True,timeline))
        chunks=[]
        deadline=time.monotonic()+10
        try:
            while True:
                # Irregular read lengths exercise partial chunk consumption.
                chunk=worker.take_audio(13007)
                if chunk: chunks.append(chunk)
                count,_,eof,error=worker.status()
                if error: raise RuntimeError(error)
                if eof and not count: break
                if time.monotonic()>deadline: raise TimeoutError('Audio worker stalled')
                time.sleep(.001)
        finally:
            worker.close()
            worker.thread.join(2)
        actual=np.frombuffer(b''.join(chunks),dtype=dtype)
        first=round(start*48000)
        last=round((start+length)*48000)
        raw=subprocess.check_output([str(ffmpeg),'-v','error','-i',source,'-map','0:a:0','-af',
             f'apad,atrim=start_sample={first}:end_sample={last},asetpts=PTS-STARTPTS',
             '-ac','2','-ar','48000','-f','f32le' if fmt=='flt' else 's16le','-'],timeout=30)
        expected=np.frombuffer(raw,dtype=dtype)
        passed=np.array_equal(actual,expected)
        result={'format':fmt,'start_seconds':start,'samples_per_channel':len(actual)//2,
                'expected_samples_per_channel':len(expected)//2,'identical_to_ffmpeg':passed,
                'peak':float(np.max(np.abs(actual.astype(np.float64))))}
        checks.append(result)
        print(result,flush=True)
report={'checks':checks,'rounded_timestamps_corrected':timeline['rounded_timestamps_corrected'],
        'status':'pass' if all(c['identical_to_ffmpeg'] for c in checks) else 'fail',
        'scope':'PCM entering QAudioSink; does not record physical device output.'}
(ROOT/'artifacts'/'splicelet-audio-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
sys.exit(0 if report['status']=='pass' else 1)
