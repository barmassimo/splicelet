"""Two lanes with automatic crossfades, globally linked until explicitly unlinked."""
from .editing import Clips


class Tracks:
    def __init__(self,video,audio=None,linked=True):
        self.video = video
        self.audio = audio or Clips(video.frame_count,video.times,video.source_duration)
        if audio is None:
            self.audio.clips = video.clips.copy()
            self.audio.origin,self.audio.extent = video.origin,video.extent
            self.audio.next_id = video.next_id
        self.linked = linked
        self.lane = 'video'
        self.undo_stack,self.redo_stack = [],[]

    @property
    def active(self): return getattr(self,self.lane)
    @property
    def other(self): return self.audio if self.lane=='video' else self.video
    @property
    def selected_ids(self): return self.active.selected_ids
    @selected_ids.setter
    def selected_ids(self,value): self.active.selected_ids = value
    def __getattr__(self,name): return getattr(self.active,name)

    def activate(self,lane):
        if lane!=self.lane:
            selection = self.active.selected_ids.copy() if self.linked else set()
            anchor = self.active.selection_anchor if self.linked else None
            self.active.selected_ids.clear()
            self.lane = lane
            self.active.selected_ids = selection
            self.active.selection_anchor = anchor

    def snapshot(self):
        return (self.video.snapshot(),self.audio.snapshot(),self.linked,self.lane,
                self.video.next_id,self.audio.next_id)

    def restore_snapshot(self,state):
        video,audio,self.linked,self.lane,vi,ai = state
        for model,data,next_id in ((self.video,video,vi),(self.audio,audio,ai)):
            clips,selected,model.extent,model.origin = data
            model.clips,model.selected_ids = clips.copy(),selected.copy()
            model.next_id = next_id
            model.selection_anchor = next((c.uid for c in clips if c.uid in selected),None)
            model.undo_stack.clear(); model.redo_stack.clear()

    def _edit(self,command,*args):
        before = self.snapshot()
        model,other = self.active,self.other
        model.next_id = max(model.next_id,other.next_id)
        if not getattr(model,command)(*args): return False
        if self.linked:
            other.clips = model.clips.copy()
            other.origin,other.extent = model.origin,model.extent
        elif command=='add_space':
            other.origin,other.extent = model.origin,model.extent
        origin = min(model.origin,other.origin)
        if command in ('remove_gap','move_selection','resize'):
            extent = max(model.extent,max((other.end(c) for c in other.clips),default=origin))
        else:
            extent = max(model.extent,other.extent)
        next_id = max(model.next_id,other.next_id)
        for lane in (model,other):
            lane.origin,lane.extent = origin,extent
            lane.next_id = next_id
            lane.undo_stack.clear(); lane.redo_stack.clear()
        self.undo_stack.append(before); self.redo_stack.clear()
        return True

    def unlink(self):
        if not self.linked: return False
        self.undo_stack.append(self.snapshot()); self.redo_stack.clear()
        self.linked = False
        return True

    def insert_source(self,source,position):
        """Place a source without ripple; linked lanes share a black/silent partner."""
        from .editing import Clip
        from fractions import Fraction
        position = Fraction(str(position))+self.origin
        if position<self.origin: return False
        uid = max(self.video.next_id,self.audio.next_id)
        clip = Clip(uid,position,((source.first,source.end),))
        targets = (self.video,self.audio) if self.linked else (self.active,)
        for model in targets:
            if not model.valid_overlaps(sorted([*model.clips,clip],key=lambda c:c.start)): return False
        self.undo_stack.append(self.snapshot()); self.redo_stack.clear()
        for model in targets:
            model.clips.append(clip); model.clips.sort(key=lambda c:c.start)
            model.selected_ids = {uid}; model.selection_anchor = uid
        extent = max(self.extent,*(model.end(clip) for model in targets))
        for model in (self.video,self.audio):
            model.next_id = uid+1; model.extent = extent
        return True

    def split_at(self,position): return self._edit('split_at',position)
    def move_selection(self,index,target): return self._edit('move_selection',index,target)
    def resize(self,index,side,position): return self._edit('resize',index,side,position)
    def duplicate(self,index): return self._edit('duplicate',index)
    def join(self): return self._edit('join')
    def delete_selected(self): return self._edit('delete_selected')
    def remove_gap(self,index): return self._edit('remove_gap',index)
    def add_space(self,side,seconds): return self._edit('add_space',side,seconds)
    def rename(self,text): return self._edit('rename',text)
    def set_fade(self,key,value): return self._edit('set_fade',key,value)
    def frames(self,fps=30): return self.video.frames(fps)
    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.snapshot()); self.restore_snapshot(self.undo_stack.pop())
    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.snapshot()); self.restore_snapshot(self.redo_stack.pop())
