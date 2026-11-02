"""Qt-independent project intervals and PTS schedules for automatic crossfades."""
from bisect import bisect_left
import heapq
import math


def intervals(parts,duration):
    events = {0.:([],[]),duration:([],[])}
    for i,part in enumerate(parts):
        if part.end<=0 or part.start>=duration: continue
        events.setdefault(max(0.,part.start),([],[]))[0].append((i,part))
        events.setdefault(min(duration,part.end),([],[]))[1].append(i)
    edges = sorted(events)
    active = {}
    for start,end in zip(edges,edges[1:]):
        added,removed = events[start]
        for i in removed: active.pop(i,None)
        active.update(added)
        if end>start: yield start,end,tuple(active.values())


def interval_frames(active,times,start,end,fps):
    """Union of contributing source PTS; hold a frame at newly exposed edges."""
    def source(part):
        first = max(part.first_frame,bisect_left(times,part.source_start+start-part.start-1e-9))
        for i in range(first,part.end_frame):
            stamp = part.start+float(times[i])-part.source_start
            if stamp>=end-1e-9: break
            if stamp>start+1e-9: yield stamp
    def gap():
        for i in range(1,math.ceil((end-start)*fps)):
            stamp = start+i/fps
            if stamp<end-1e-9: yield stamp
    yield start
    previous = start
    for stamp in heapq.merge(*(source(p) for p in active)) if active else gap():
        if stamp>previous+1e-9:
            yield stamp
            previous = stamp


def frame_schedule(parts,times,duration,fps):
    for start,end,active in intervals(parts,duration):
        yield from interval_frames(active,times,start,end,fps)
