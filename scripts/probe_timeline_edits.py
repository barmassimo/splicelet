"""Delete -> gap -> move -> join, verified through actual decoders and MP4 export."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import av
import numpy as np
from PySide6.QtCore import QCoreApplication
from splicelet.editing import Clips
from splicelet.source import Job,Decoder,inspect_and_index
from splicelet.exporting import ExportSpec,ExportTask

app=QCoreApplication([])
out=ROOT/'artifacts'/'timeline-tests'
out.mkdir(parents=True,exist_ok=True)
run=Path(tempfile.mkdtemp(prefix='run-',dir=out))
source=run/'source.mkv'
ffmpeg=Path(sys.executable).parent/'Library/bin/ffmpeg.exe'
checks=[]
def record(name,**details):
    checks.append({'name':name,'status':'pass',**details});print('PASS',name,details,flush=True)

def read_worker(kind,model,position=0,duration=None):
    worker=Decoder(kind)
    job=Job(1,str(source),position,0.,float(model.duration) if duration is None else duration,True,data['metadata']['audio_timeline'],(),model.parts(),30.,320,180)
    worker.request(1,job)
    result=[]; deadline=time.monotonic()+15
    try:
        while True:
            item=worker.take_video() if kind=='video' else worker.take_audio(65536)
            if item is not None and item!=b'': result.append(item)
            count,_,eof,error=worker.status()
            assert not error,error
            if eof and not count: break
            assert time.monotonic()<deadline,'Decoder timeout'
            if item is None or item==b'':time.sleep(.001)
    finally:
        worker.close();worker.thread.join(2)
    return result

try:
    subprocess.run([str(ffmpeg),'-v','error','-n','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=6',
                    '-f','lavfi','-i','aevalsrc=0.25*sin(2*PI*440*t)|0.125*sin(2*PI*880*t):s=48000:d=6',
                    '-c:v','libx264','-crf','18','-threads','4','-g','30','-c:a','pcm_s24le',str(source)],check=True,timeout=30)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    data={}
    inspect_and_index(str(source),threading.Event(),lambda kind,value:data.__setitem__(kind,value))
    base=Fraction(data['index']['time_base'])
    times=[pts*base for pts in data['index']['pts']]
    model=Clips(180,times,6)
    assert model.split(60) and model.split(120)
    model.select(1);assert model.delete_selected()
    assert [(float(c.start),float(model.end(c))) for c in model.clips]==[(0.,2.),(4.,6.)]
    frames=read_worker('video',model)
    assert len(frames)==180,len(frames)
    with av.open(str(source)) as c:
        expected=[frame.to_ndarray(format='rgb24').tobytes() for frame in c.decode(video=0)]
    for index,(_,stamp,image) in enumerate(frames):
        actual=bytes(image.constBits())
        if 60<=index<120: assert not any(actual),'Gap is not black'
        else: assert actual==expected[index],index
    audio=np.frombuffer(b''.join(read_worker('audio',model)),dtype='<f4')
    original=np.frombuffer(subprocess.check_output([str(ffmpeg),'-v','error','-i',str(source),'-map','0:a:0','-f','f32le','-']),dtype='<f4')
    assert len(audio)==len(original)
    assert np.array_equal(audio[:2*48000*2],original[:2*48000*2])
    assert not np.any(audio[2*48000*2:4*48000*2])
    assert np.array_equal(audio[4*48000*2:],original[4*48000*2:])
    record('deleted_clip_is_black_and_silent_without_ripple',frames=len(frames))

    before_gap=model.snapshot()
    assert model.gaps()==((Fraction(2),Fraction(4)),)
    assert model.remove_gap(0) and model.duration==4
    assert [c.start for c in model.clips]==[0,2] and not model.gaps()
    closed=read_worker('video',model)
    assert len(closed)==120
    for i,(_,stamp,image) in enumerate(closed):
        assert bytes(image.constBits())==expected[i if i<60 else i+60]
    closed_audio=np.frombuffer(b''.join(read_worker('audio',model)),dtype='<f4')
    assert np.array_equal(closed_audio,np.concatenate((original[:2*48000*2],original[4*48000*2:])))
    model.undo(); assert model.snapshot()==before_gap
    model.redo(); assert model.duration==4
    model.undo()
    record('remove_gap_preserves_exact_video_audio_and_supports_undo_redo')

    ends=Clips(180,times,6); ends.split(60); ends.split(120)
    ends.select(0); ends.select(2,True); ends.delete_selected()
    assert ends.gaps()==((0,2),(4,6))
    selected=ends.selected_ids.copy()
    assert ends.remove_gap(0) and ends.clips[0].start==0 and ends.duration==4
    assert ends.selected_ids==selected and ends.remove_gap(0) and ends.duration==2
    assert not ends.gaps()
    ends.select(0); ends.delete_selected(); assert ends.remove_gap(0)
    assert ends.duration==0 and ends.frames()==()
    ends.undo(); assert ends.duration==2
    record('leading_trailing_and_entire_empty_gaps_close_safely')

    model.select(0);model.select(1,True)
    assert not model.can_join and not model.join()
    assert model.move(1,2)
    assert model.can_join and model.join()
    assert model.selected_clip.pieces==((0,60),(120,180))
    frames=read_worker('video',model,duration=4)
    assert len(frames)==120,len(frames)
    for index,(_,stamp,image) in enumerate(frames):
        assert bytes(image.constBits())==expected[index if index<60 else index+60]
    audio=np.frombuffer(b''.join(read_worker('audio',model,duration=4)),dtype='<f4')
    reference=np.concatenate([original[:2*48000*2],original[4*48000*2:]])
    assert np.array_equal(audio,reference)
    record('moved_and_joined_preview_skips_deleted_material',frames=len(frames))

    clip=model.selected_clip
    spec=ExportSpec(str(source),0,180,0,6000,base,0.,data['metadata']['audio_timeline'],clip.fades,model.parts(clip),0.,4.)
    result,message=ExportTask()._execute(spec,run/'joined.mp4')
    assert result=='success',message
    errors=[];timestamps=[]
    with av.open(str(run/'joined.mp4')) as c:
        for index,frame in enumerate(c.decode(video=0)):
            target=np.frombuffer(expected[index if index<60 else index+60],dtype=np.uint8).astype(np.float32)
            actual=frame.to_ndarray(format='rgb24').astype(np.float32).reshape(-1)
            errors.append(float(np.mean((actual-target)**2)))
            timestamps.append(float(frame.pts*frame.time_base))
    assert len(errors)==120,len(errors)
    assert max(errors)<100,max(errors)
    assert abs(timestamps[60]-2.)<.001,timestamps[60]
    with av.open(str(run/'joined.mp4')) as c:
        audio_stream=c.streams.audio[0]
        assert abs(float(audio_stream.duration*audio_stream.time_base)-4.)<.001
    record('joined_export_contains_only_first_and_third_source_ranges',frames=len(errors),second_part_time=timestamps[60])

    model.undo();assert len(model.clips)==2 and model.clips[1].start==2
    model.undo();assert model.clips[1].start==4
    model.undo();assert len(model.clips)==3
    model.redo();assert len(model.clips)==2
    assert model.move(1,1) and model.has_overlaps
    model.undo()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    record('undo_redo_automatic_overlap_and_source_integrity')

    reordered=Clips(180,times,6)
    reordered.split(60);reordered.split(120);reordered.select(1);reordered.delete_selected()
    assert reordered.move(0,6) and reordered.move(0,0) and reordered.move(1,2)
    reordered.select(0);reordered.select(1,True);assert reordered.join()
    clip=reordered.selected_clip
    assert clip.pieces==((120,180),(0,60))
    reverse=ExportSpec(str(source),120,60,4000,2000,base,0.,data['metadata']['audio_timeline'],clip.fades,reordered.parts(clip),0.,4.)
    result,message=ExportTask()._execute(reverse,run/'reordered.mp4')
    assert result=='success',message
    with av.open(str(run/'reordered.mp4')) as c:
        frames=list(c.decode(video=0))
    assert len(frames)==120
    for index,frame in enumerate(frames):
        source_index=index+120 if index<60 else index-60
        target=np.frombuffer(expected[source_index],dtype=np.uint8).astype(np.float32)
        actual=frame.to_ndarray(format='rgb24').astype(np.float32).reshape(-1)
        assert float(np.mean((actual-target)**2))<100
    record('reordered_join_exports_in_timeline_order_not_source_order')

    trimmed=Clips(180,times,6)
    trimmed.split(90);trimmed.select(1);trimmed.delete_selected()
    assert trimmed.resize(0,'right',4)
    assert trimmed.selected_clip.pieces==((0,120),) and trimmed.end(trimmed.selected_clip)==4
    frames=read_worker('video',trimmed)
    assert len(frames)==120
    assert all(bytes(image.constBits())==expected[i] for i,(_,_,image) in enumerate(frames))
    assert trimmed.resize(0,'left',1)
    assert trimmed.selected_clip.pieces==((30,120),) and trimmed.selected_clip.start==1
    assert trimmed.resize(0,'left',0)
    assert trimmed.selected_clip.pieces==((0,120),)
    assert trimmed.resize(0,'right',100) and trimmed.selected_clip.pieces==((0,180),)
    trimmed.undo();assert trimmed.selected_clip.pieces==((0,120),)
    record('edge_trim_reveals_original_tail_and_restores_left_edge_without_stretch')

    bounded=Clips(180,times,6);bounded.split(60);bounded.split(120)
    bounded.select(1);bounded.delete_selected()
    original_last=bounded.clips[1]
    assert bounded.resize(0,'right',5)
    assert bounded.end(bounded.clips[0])==5 and bounded.clips[1]==original_last
    assert bounded.resize(1,'left',0) is False
    assert bounded.resize(0,'right',0)
    assert bounded.clips[0].pieces==((0,1),)
    record('resize_allows_crossfade_preserves_source_limits_and_one_frame_minimum')

    duplicate=Clips(180,times,6);duplicate.split(60);duplicate.split(120)
    duplicate.select(1)
    snapshot=duplicate.snapshot()
    assert not duplicate.duplicate() and duplicate.snapshot()==snapshot
    duplicate.select(0)
    original_starts={c.uid:c.start for c in duplicate.clips}
    assert duplicate.duplicate()
    assert duplicate.origin==-2 and duplicate.duration==8
    assert all(c.start==original_starts[c.uid] for c in duplicate.clips if c.uid in original_starts)
    frames=read_worker('video',duplicate)
    expected_order=list(range(60))+list(range(180))
    assert len(frames)==240
    assert all(bytes(image.constBits())==expected[expected_order[i]] for i,(_,_,image) in enumerate(frames))
    audio=np.frombuffer(b''.join(read_worker('audio',duplicate)),dtype='<f4')
    assert np.array_equal(audio,np.concatenate([original[:2*48000*2],original]))
    record('first_duplicate_extends_project_left_without_moving_existing_clips')
    starts={c.uid:c.start for c in duplicate.clips}
    duplicate.select(len(duplicate.clips)-1);assert duplicate.duplicate()
    assert duplicate.duration==10 and all(c.start==starts[c.uid] for c in duplicate.clips if c.uid in starts)
    duplicate.undo();assert duplicate.duration==8
    duplicate.undo();assert duplicate.duration==6 and duplicate.origin==0
    record('last_duplicate_extends_right_and_undo_restores_origin')

    spaces=Clips(180,times,6)
    for frame in (30,90,120):spaces.split(frame)
    spaces.select(2);spaces.delete_selected();spaces.select(1)
    assert not spaces.duplicate()
    spaces=Clips(180,times,6)
    for frame in (30,60,120):spaces.split(frame)
    spaces.select(2);spaces.delete_selected();spaces.select(1)
    old={c.uid:c.start for c in spaces.clips}
    assert spaces.duplicate() and spaces.selected_clip.start==2
    assert all(c.start==old[c.uid] for c in spaces.clips if c.uid in old)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    record('interior_duplicate_requires_sufficient_adjacent_gap_without_ripple')

    compound=Clips(180,times,6);compound.split(60);compound.split(120)
    compound.select(1);compound.delete_selected();compound.move(1,2)
    compound.select(0);compound.select(1,True);compound.join()
    assert compound.selected_clip.pieces==((0,60),(120,180))
    assert compound.resize(0,'right',1)
    assert compound.resize(0,'right',4)
    assert compound.selected_clip.pieces==((0,60),(120,180))
    assert compound.resize(0,'left',3)
    assert compound.resize(0,'left',0)
    assert compound.selected_clip.pieces==((0,60),(120,180))
    record('reextending_trimmed_join_restores_edited_ranges_not_deleted_middle')

    group=Clips(180,times,6); group.split(60); group.split(120)
    assert group.move(2,8) and group.move(1,4)
    group.select(0); group.select(1,False,True)
    assert group.move_selection(1,5)
    assert [c.start for c in group.clips]==[1,5,8]
    frames=read_worker('video',group)
    expected_frames=[None]*300
    for a,b,first in ((30,90,0),(150,210,60),(240,300,120)):
        expected_frames[a:b]=range(first,first+b-a)
    assert len(frames)==len(expected_frames)
    for (_,stamp,image),source_frame in zip(frames,expected_frames):
        if source_frame is None: assert not any(bytes(image.constBits()))
        else: assert bytes(image.constBits())==expected[source_frame]
    group_audio=np.frombuffer(b''.join(read_worker('audio',group)),dtype='<f4')
    reference=np.zeros(10*48000*2,dtype='<f4')
    for project_start,source_start in ((1,0),(5,2),(8,4)):
        reference[project_start*48000*2:(project_start+2)*48000*2]=original[source_start*48000*2:(source_start+2)*48000*2]
    assert np.array_equal(group_audio,reference)
    record('group_move_preserves_exact_source_frames_samples_and_internal_black_silent_gaps')

    space=Clips(180,times,6)
    space.add_space('start','.25'); space.add_space('end','.5')
    frames=read_worker('video',space)
    source_stamps={round(float(stamp),9):i for i,stamp in enumerate(times)}
    for _,stamp,image in frames:
        if stamp<.25-.000001 or stamp>=6.25-.000001:
            assert not any(bytes(image.constBits()))
        else:
            assert bytes(image.constBits())==expected[source_stamps[round(stamp-.25,9)]]
    samples=np.frombuffer(b''.join(read_worker('audio',space)),dtype='<f4')
    reference=np.concatenate((np.zeros(12000*2,dtype='<f4'),original,np.zeros(24000*2,dtype='<f4')))
    assert np.array_equal(samples,reference)
    record('added_edge_space_is_black_and_exact_silence_with_unchanged_source_frames_samples')



    copied=Clips(180,times,6);copied.split(60);copied.split(120)
    copied.select(0);copied.duplicate();copied.select(0);copied.select(1,True);copied.join()
    clip=copied.selected_clip
    repeat=ExportSpec(str(source),0,60,0,2000,base,0.,data['metadata']['audio_timeline'],clip.fades,copied.parts(clip),0.,4.)
    result,message=ExportTask()._execute(repeat,run/'duplicated.mp4')
    assert result=='success',message
    with av.open(str(run/'duplicated.mp4')) as c:
        repeated=list(c.decode(video=0))
    assert len(repeated)==120
    for i,frame in enumerate(repeated):
        target=np.frombuffer(expected[i%60],dtype=np.uint8).astype(np.float32)
        actual=frame.to_ndarray(format='rgb24').astype(np.float32).reshape(-1)
        assert float(np.mean((actual-target)**2))<100
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    record('duplicated_and_joined_clip_exports_both_copies')
except Exception:
    import traceback
    checks.append({'name':'failure','status':'fail','error':traceback.format_exc()})
finally:
    report={'checks':checks,'status':'pass' if all(c['status']=='pass' for c in checks) else 'fail','output_directory':str(run)}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
sys.exit(0 if report['status']=='pass' else 1)
