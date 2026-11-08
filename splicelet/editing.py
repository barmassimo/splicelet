"""Non-destructive timeline: immutable clips refer to one or more source ranges."""
from bisect import bisect_right,bisect_left
from copy import copy
from dataclasses import dataclass,replace
from fractions import Fraction
import math
from .effects import Fades, EffectSpan


@dataclass(frozen=True)
class Part:
    start: float
    end: float
    source_start: float
    source_end: float
    first_frame: int
    end_frame: int
    clip_id: int = -1


@dataclass(frozen=True)
class Clip:
    uid: int
    start: Fraction
    pieces: tuple
    fades: Fades = Fades()
    left_reserve: tuple = ()
    right_reserve: tuple = ()
    name: str = ""
    components: tuple = ()


class Clips:
    def __init__(self,frame_count,times=None,duration=None):
        self.frame_count = frame_count
        self.times = tuple(Fraction(str(t)) for t in times) if times is not None else tuple(map(Fraction,range(frame_count)))
        self.source_duration = Fraction(str(duration)) if duration is not None else Fraction(frame_count)
        self.edges = (*self.times,self.source_duration)
        self.clips = [Clip(0,Fraction(0),((0,frame_count),))]
        self.selected_ids = {0}
        self.selection_anchor = 0
        self.extent = self.source_duration
        self.origin = Fraction(0)
        self.next_id = 1
        self.sources = ()
        self.undo_stack,self.redo_stack = [],[]

    @property
    def cuts(self): return [clip.pieces[0][0] for clip in self.clips[1:]]
    @property
    def boundaries(self): return [0,*self.cuts,self.frame_count]
    @property
    def effects(self): return [clip.fades for clip in self.clips]
    @property
    def selected_indices(self): return {i for i,c in enumerate(self.clips) if c.uid in self.selected_ids}
    @property
    def selected(self):
        indices = self.selected_indices
        return next(iter(indices)) if len(indices)==1 else -1
    @property
    def selected_clip(self):
        if self.selected<0: raise ValueError('Select exactly one clip.')
        return self.clips[self.selected]
    @property
    def selected_frames(self):
        pieces = self.selected_clip.pieces
        return pieces[0][0],pieces[-1][1]

    @property
    def selected_length(self):
        total,edge = Fraction(0),None
        for clip in sorted((c for c in self.clips if c.uid in self.selected_ids),key=lambda c:c.start):
            end = self.end(clip)
            total += max(Fraction(0),end-max(clip.start,edge if edge is not None else clip.start))
            edge = max(edge,end) if edge is not None else end
        return total

    def length(self,clip):
        if clip.components: return max(self.end(c) for c in clip.components)
        return sum((self.edges[b]-self.edges[a] for a,b in clip.pieces),Fraction(0))

    def constituents(self,clip):
        return tuple(replace(c,start=c.start+clip.start) for c in clip.components) if clip.components else (clip,)

    def render_clips(self,clips=None):
        """Flatten edit groups without changing source ranges or fade clocks."""
        result = []
        for clip in self.clips if clips is None else clips:
            for child in self.constituents(clip):
                result.append(replace(child,uid=-len(result)-2) if clip.components else child)
        return result

    def compound(self,template,children):
        start = children[0].start
        return replace(template,start=start,
                       pieces=tuple(p for c in children for p in c.pieces),
                       components=tuple(replace(c,start=c.start-start) for c in children),
                       fades=Fades(children[0].fades.audio_in,children[-1].fades.audio_out,
                                   children[0].fades.video_in,children[-1].fades.video_out),
                       left_reserve=children[0].left_reserve,right_reserve=children[-1].right_reserve)

    def _component_model(self,clip):
        model = copy(self)
        model.clips = [replace(c,uid=i) for i,c in enumerate(self.constituents(clip))]
        model.next_id = len(model.clips)
        model.selected_ids = set()
        model.selection_anchor = None
        model.undo_stack,model.redo_stack = [],[]
        return model
    def end(self,clip): return clip.start+self.length(clip)
    @property
    def duration(self): return self.extent-self.origin
    def project_start(self,clip): return clip.start-self.origin
    def project_end(self,clip): return self.end(clip)-self.origin
    def snapshot(self): return self.clips.copy(),self.selected_ids.copy(),self.extent,self.origin
    def remember(self):
        self.undo_stack.append(self.snapshot()); self.redo_stack.clear()
    def select(self,index,toggle=False,extend_range=False):
        if not 0<=index<len(self.clips): return
        uid = self.clips[index].uid
        if extend_range and self.selected_ids:
            anchor = next((i for i,c in enumerate(self.clips) if c.uid==self.selection_anchor),min(self.selected_indices,default=index))
            selected = {c.uid for c in self.clips[min(anchor,index):max(anchor,index)+1]}
            if toggle: self.selected_ids.update(selected)
            else: self.selected_ids = selected
            self.selection_anchor = self.clips[anchor].uid
        else:
            if toggle: self.selected_ids.symmetric_difference_update({uid})
            else: self.selected_ids = {uid}
            self.selection_anchor = uid

    def moving_indices(self,index):
        """A selected group must be consecutive in clip order; gaps are allowed."""
        if not 0<=index<len(self.clips): return ()
        if self.clips[index].uid not in self.selected_ids: return (index,)
        indices = sorted(self.selected_indices)
        return tuple(indices) if indices==list(range(indices[0],indices[-1]+1)) else ()

    def valid_overlaps(self,clips):
        """Transitions connect two ordered edges; nesting/triple mixes are excluded."""
        groups = sorted(clips,key=lambda c:c.start)
        if any(b.start<=a.start or self.end(b)<=self.end(a) for a,b in zip(groups,groups[1:])): return False
        ordered = sorted(self.render_clips(clips),key=lambda c:c.start)
        for i,clip in enumerate(ordered):
            if clip.start<self.origin: return False
            if i and (clip.start<=ordered[i-1].start or self.end(clip)<=self.end(ordered[i-1])): return False
            if i>=2 and clip.start<self.end(ordered[i-2]): return False
        return True

    @property
    def has_overlaps(self):
        clips = self.render_clips()
        return any(b.start<self.end(a) for a,b in zip(clips,clips[1:]))

    def effect_spans(self):
        clips = self.render_clips()
        return tuple(EffectSpan(float(self.project_start(c)),float(self.project_end(c)),c.fades,
                     float(max(Fraction(0),self.end(clips[i-1])-c.start)) if i else 0.,
                     float(max(Fraction(0),self.end(c)-clips[i+1].start)) if i+1<len(clips) else 0.,c.uid)
                     for i,c in enumerate(clips))

    def move_selection(self,index,target):
        indices = self.moving_indices(index)
        if not indices: return False
        if len(indices)==1: return self.move(index,target)
        first,last = self.clips[indices[0]],self.clips[indices[-1]]
        delta = max(self.origin-first.start,Fraction(str(target))+self.origin-self.clips[index].start)
        if abs(delta)<Fraction(1,1000000): return False
        start,end = first.start+delta,self.end(last)+delta
        ids = {self.clips[i].uid for i in indices}
        # Outsiders cannot be inserted into the moving block's internal gaps.
        if any(start<=c.start and self.end(c)<=end for c in self.clips if c.uid not in ids): return False
        candidates = [replace(c,start=c.start+delta) if c.uid in ids else c for c in self.clips]
        if not self.valid_overlaps(candidates): return False
        self.remember()
        self.clips = candidates
        self.clips.sort(key=lambda c:c.start)
        self.extent = max(self.end(c) for c in self.clips)
        return True

    def split(self,frame):
        if not 0<frame<self.frame_count: return False
        return self.split_at(self.times[frame]-self.origin)

    def split_at(self,position):
        position = Fraction(str(position))+self.origin
        for index,clip in enumerate(self.clips):
            if not clip.start<position<self.end(clip): continue
            if clip.components:
                expanded = self._component_model(clip)
                boundary = position
                if expanded.split_at(position-self.origin): boundary = expanded.selected_clip.start
                left = [c for c in expanded.clips if self.end(c)<=boundary+Fraction(1,1000000)]
                right = [c for c in expanded.clips if c.start>=boundary-Fraction(1,1000000)]
                if not left or not right or len(left)+len(right)!=len(expanded.clips): return False
                first = self.compound(clip,left)
                second = self.compound(replace(clip,uid=self.next_id),right)
                if not self.valid_overlaps(self.clips[:index]+[first,second]+self.clips[index+1:]): return False
                self.remember(); self.next_id += 1
                self.clips[index:index+1] = [first,second]
                self.selected_ids = {second.uid}; self.selection_anchor = second.uid
                return True
            left,right = [],[]
            elapsed = Fraction(0)
            for a,b in clip.pieces:
                length = self.edges[b]-self.edges[a]
                offset = position-clip.start-elapsed
                if offset<=0: right.append((a,b))
                elif offset>=length: left.append((a,b))
                else:
                    frame = min(b,max(a,bisect_right(self.times,self.edges[a]+offset+Fraction(1,1000000))-1))
                    if frame>a: left.append((a,frame))
                    if frame<b: right.append((frame,b))
                elapsed += length
            if not left or not right: return False
            first = replace(clip,pieces=tuple(left),fades=replace(clip.fades,audio_out=0.,video_out=0.),right_reserve=tuple(right)+clip.right_reserve)
            second = Clip(self.next_id,self.end(first),tuple(right),replace(clip.fades,audio_in=0.,video_in=0.),clip.left_reserve+tuple(left),clip.right_reserve,clip.name)
            if not self.valid_overlaps(self.clips[:index]+[first,second]+self.clips[index+1:]): return False
            self.remember()
            self.next_id += 1
            self.clips[index:index+1] = [first,second]
            self.selected_ids = {second.uid}
            self.selection_anchor = second.uid
            return True
        return False

    @property
    def can_join(self):
        indices = sorted(self.selected_indices)
        return len(indices)==2 and indices[1]==indices[0]+1 and self.clips[indices[1]].start<=self.end(self.clips[indices[0]])+Fraction(1,1000000)

    def join(self):
        if not self.can_join: return False
        self.remember()
        a,b = sorted(self.selected_indices)
        left,right = self.clips[a],self.clips[b]
        if left.components or right.components or right.start<self.end(left):
            merged = self.compound(left,self.constituents(left)+self.constituents(right))
            self.clips[a:b+1] = [merged]
            self.selected_ids = {merged.uid}; self.selection_anchor = merged.uid
            return True
        pieces = []
        for first,last in left.pieces+right.pieces:
            if pieces and pieces[-1][1]==first: pieces[-1] = (pieces[-1][0],last)
            else: pieces.append((first,last))
        merged = replace(left,pieces=tuple(pieces),fades=Fades(left.fades.audio_in,right.fades.audio_out,left.fades.video_in,right.fades.video_out),right_reserve=right.right_reserve)
        self.clips[a:b+1] = [merged]
        self.selected_ids = {merged.uid}
        self.selection_anchor = merged.uid
        return True

    def delete_selected(self):
        if not self.selected_ids: return False
        self.remember()
        self.clips = [c for c in self.clips if c.uid not in self.selected_ids]
        self.selected_ids.clear()
        self.selection_anchor = None
        return True

    def gaps(self):
        """Empty intervals in normalized project time, including either end."""
        result = []
        cursor = self.origin
        for clip in self.clips:
            if clip.start>cursor: result.append((cursor-self.origin,clip.start-self.origin))
            cursor = max(cursor,self.end(clip))
        if self.extent>cursor: result.append((cursor-self.origin,self.extent-self.origin))
        return tuple(result)

    def add_space(self,side,seconds):
        if side not in ('start','end'): raise ValueError('Choose project start or end.')
        try:
            duration = Fraction(str(seconds))
        except (ValueError,ZeroDivisionError,OverflowError):
            raise ValueError('Enter a positive number of seconds using a decimal point.') from None
        if duration<=0: raise ValueError('Enter a positive number of seconds using a decimal point.')
        self.remember()
        if side=='start': self.origin -= duration
        else: self.extent += duration
        return True

    def remove_gap(self,index):
        gaps = self.gaps()
        if not 0<=index<len(gaps): return False
        start,end = gaps[index]
        length = end-start
        self.remember()
        self.clips = [replace(c,start=c.start-length) if c.start>=end+self.origin else c for c in self.clips]
        self.extent -= length
        return True

    def move(self,index,target):
        if not 0<=index<len(self.clips): return False
        clip = self.clips[index]
        target = max(self.origin,Fraction(str(target))+self.origin)
        if abs(target-clip.start)<Fraction(1,1000000): return False
        if not self.valid_overlaps([replace(c,start=target) if c.uid==clip.uid else c for c in self.clips]): return False
        self.remember()
        if clip.uid not in self.selected_ids:
            self.selected_ids = {clip.uid}
            self.selection_anchor = clip.uid
        self.clips[index] = replace(clip,start=target)
        self.clips.sort(key=lambda c:c.start)
        self.extent = max(self.end(item) for item in self.clips)
        return True

    def duplicate(self,index=None):
        if index is None: index = self.selected
        if not 0<=index<len(self.clips): return False
        clip = self.clips[index]
        length = self.length(clip)
        following = self.clips[index+1].start if index+1<len(self.clips) else None
        previous = self.end(self.clips[index-1]) if index else None
        if following is None or self.end(clip)+length<=following+Fraction(1,1000000):
            start = self.end(clip)
        elif previous is None or clip.start-length>=previous-Fraction(1,1000000):
            start = clip.start-length
        else: return False
        self.remember()
        copy = replace(clip,uid=self.next_id,start=start)
        self.next_id += 1
        self.clips.append(copy); self.clips.sort(key=lambda item:item.start)
        self.selected_ids = {copy.uid}
        self.selection_anchor = copy.uid
        self.origin = min(self.origin,start)
        self.extent = max(self.extent,self.end(copy))
        return True

    def _nearest(self,value,first,last):
        index = bisect_left(self.edges,value)
        candidates = {max(first,min(last,index)),max(first,min(last,index-1))}
        return min(candidates,key=lambda i:abs(self.edges[i]-value))

    @staticmethod
    def _merge(pieces):
        result = []
        for a,b in pieces:
            if result and result[-1][1]==a: result[-1] = (result[-1][0],b)
            else: result.append((a,b))
        return tuple(result)

    def _prefix(self,pieces,length,floor=False):
        kept = []
        for a,b in pieces:
            duration = self.edges[b]-self.edges[a]
            if length>=duration-Fraction(1,1000000):
                kept.append((a,b)); length -= duration
            else:
                if length<=Fraction(1,1000000) and kept: break
                edge = max(a if kept else a+1,min(b,bisect_right(self.edges,self.edges[a]+length+Fraction(1,1000000))-1)) if floor else self._nearest(self.edges[a]+length,a if kept else a+1,b)
                if edge>a: kept.append((a,edge))
                break
        return self._merge(kept)

    def _suffix(self,pieces,length,floor=False):
        kept = []
        for a,b in reversed(pieces):
            duration = self.edges[b]-self.edges[a]
            if length>=duration-Fraction(1,1000000):
                kept.insert(0,(a,b)); length -= duration
            else:
                if length<=Fraction(1,1000000) and kept: break
                edge = max(a,min(b if kept else b-1,bisect_left(self.edges,self.edges[b]-length-Fraction(1,1000000)))) if floor else self._nearest(self.edges[b]-length,a,b if kept else b-1)
                if edge<b: kept.insert(0,(edge,b))
                break
        return self._merge(kept)

    def _drop_prefix(self,pieces,count):
        result = []
        for a,b in pieces:
            skip = min(count,b-a)
            if a+skip<b: result.append((a+skip,b))
            count -= skip
        return self._merge(result)

    def _drop_suffix(self,pieces,count):
        reversed_pieces = tuple((-b,-a) for a,b in reversed(pieces))
        return tuple((-b,-a) for a,b in reversed(self._drop_prefix(reversed_pieces,count)))

    def _piece_length(self,pieces):
        return sum((self.edges[b]-self.edges[a] for a,b in pieces),Fraction(0))

    def resize_candidate(self,index,side,position):
        if not 0<=index<len(self.clips) or side not in ('left','right'): return None
        clip = self.clips[index]
        if clip.components:
            expanded = self._component_model(clip)
            edge = 0 if side=='left' else len(expanded.clips)-1
            candidate = expanded.resize_candidate(edge,side,position)
            if candidate is None: return None
            expanded.clips[edge] = candidate
            merged = self.compound(clip,expanded.clips)
            return merged if self.valid_overlaps(self.clips[:index]+[merged]+self.clips[index+1:]) else clip
        position = Fraction(str(position))+self.origin
        start,end = clip.start,self.end(clip)
        first_a,first_b = clip.pieces[0]
        last_a,last_b = clip.pieces[-1]
        earliest = clip.left_reserve[0][0] if clip.left_reserve else first_a
        latest = clip.right_reserve[-1][1] if clip.right_reserve else last_b
        lower,upper = 0,self.frame_count
        if self.sources:
            from .sources import source_for
            lower = source_for(self.sources,earliest).first
            upper = source_for(self.sources,max(last_a,latest-1)).end
        left = (((lower,earliest),) if earliest>lower else ())+clip.left_reserve
        right = clip.right_reserve+(((latest,upper),) if latest<upper else ())
        if side=='right':
            available = clip.pieces+right
            minimum = start+self.edges[first_a+1]-self.edges[first_a]
            maximum = start+self._piece_length(available)
            target = max(minimum,min(maximum,position))
            pieces = self._prefix(available,target-start)
            if self._piece_length(pieces)>maximum-start+Fraction(1,1000000): pieces = self._prefix(available,maximum-start,True)
            reserve = self._drop_prefix(available,sum(b-a for a,b in pieces))
            candidate = replace(clip,pieces=pieces,left_reserve=left,right_reserve=reserve)
            return candidate if self.valid_overlaps(self.clips[:index]+[candidate]+self.clips[index+1:]) else clip
        available = left+clip.pieces
        minimum = max(self.origin,end-self._piece_length(available))
        maximum = end-(self.edges[last_b]-self.edges[last_b-1])
        target = max(minimum,min(maximum,position))
        pieces = self._suffix(available,end-target)
        if self._piece_length(pieces)>end-minimum+Fraction(1,1000000): pieces = self._suffix(available,end-minimum,True)
        reserve = self._drop_suffix(available,sum(b-a for a,b in pieces))
        candidate = replace(clip,pieces=pieces,left_reserve=reserve,right_reserve=right)
        candidate = replace(candidate,start=end-self.length(candidate))
        return candidate if self.valid_overlaps(self.clips[:index]+[candidate]+self.clips[index+1:]) else clip

    def resize(self,index,side,position):
        candidate = self.resize_candidate(index,side,position)
        if candidate is None or (candidate.start==self.clips[index].start and candidate.pieces==self.clips[index].pieces): return False
        self.remember()
        self.clips[index] = candidate
        self.clips.sort(key=lambda c:c.start)
        if candidate.uid not in self.selected_ids:
            self.selected_ids = {candidate.uid}
            self.selection_anchor = candidate.uid
        self.extent = max(self.end(item) for item in self.clips)
        return True

    def rename(self,text):
        if self.selected<0: return False
        name = text.strip()
        if len(name)>120 or any(ord(c)<32 or ord(c)==127 for c in name):
            raise ValueError('Clip names must be a single line of at most 120 characters.')
        clip = self.selected_clip
        if clip.name==name: return False
        self.remember()
        self.clips[self.selected] = replace(clip,name=name)
        return True

    def set_fade(self,key,value):
        if self.selected<0 or key not in Fades.__dataclass_fields__ or not math.isfinite(value) or value<0: return False
        clip = self.selected_clip
        if getattr(clip.fades,key)==value: return False
        self.remember()
        if clip.components:
            children = list(self.constituents(clip))
            edge = 0 if key.endswith('_in') else -1
            children[edge] = replace(children[edge],fades=replace(children[edge].fades,**{key:value}))
            self.clips[self.selected] = self.compound(clip,children)
        else:
            self.clips[self.selected] = replace(clip,fades=replace(clip.fades,**{key:value}))
        return True

    def parts(self,clip=None):
        result = []
        all_clips = self.render_clips()
        if clip is not None:
            offset = sum(len(self.constituents(c)) for c in self.clips[:self.clips.index(clip)])
            all_clips = all_clips[offset:offset+len(self.constituents(clip))]
        for item in all_clips:
            cursor = self.project_start(item)
            for a,b in item.pieces:
                boundaries = [a,*[s.end for s in self.sources if a<s.end<b],b]
                for first,last in zip(boundaries,boundaries[1:]):
                    length = self.edges[last]-self.edges[first]
                    result.append(Part(float(cursor),float(cursor+length),float(self.edges[first]),float(self.edges[last]),first,last,item.uid))
                    cursor += length
        return tuple(result)

    def frames(self,fps=30):
        if self.has_overlaps:
            from .composition import frame_schedule
            return tuple((stamp,None) for stamp in frame_schedule(self.parts(),self.times,float(self.duration),fps))
        result = []
        cursor = Fraction(0)
        step = Fraction(1)/Fraction(str(fps))
        for part in self.parts():
            start = Fraction(str(part.start))
            while cursor<start-Fraction(1,1000000):
                result.append((float(cursor),None)); cursor += step
            for frame in range(part.first_frame,part.end_frame):
                result.append((float(start+self.times[frame]-self.edges[part.first_frame]),frame))
            cursor = Fraction(str(part.end))
        while cursor<self.duration-Fraction(1,1000000):
            result.append((float(cursor),None)); cursor += step
        return tuple(result)

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.snapshot())
            self.clips,self.selected_ids,self.extent,self.origin = self.undo_stack.pop()
            self.selection_anchor = next((c.uid for c in self.clips if c.uid in self.selected_ids),None)
    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.snapshot())
            self.clips,self.selected_ids,self.extent,self.origin = self.redo_stack.pop()
            self.selection_anchor = next((c.uid for c in self.clips if c.uid in self.selected_ids),None)
