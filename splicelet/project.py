"""Versioned project metadata; sources stay external and read-only."""
import json
import math
import os
from pathlib import Path
import tempfile
from fractions import Fraction

from .editing import Clip, Clips
from .effects import Fades


def rational(value):
    return [value.numerator, value.denominator]


def fraction(value):
    if not isinstance(value,list) or len(value)!=2 or any(type(v) is not int for v in value) or value[1]<=0:
        raise ValueError('Invalid rational project time.')
    return Fraction(*value)


def timeline(model):
    from .tracks import Tracks
    if isinstance(model,Tracks):
        return {'video':timeline(model.video),'audio':timeline(model.audio),'linked':model.linked}
    def ranges(pieces):
        result = []
        if not model.sources:
            return [{'source':'source-1','first':a,'end':b} for a,b in pieces]
        for a,b in pieces:
            for i,s in enumerate(model.sources):
                first,end = max(a,s.first),min(b,s.end)
                if first<end: result.append({'source':f'source-{i+1}','first':first-s.first,'end':end-s.first})
        return result
    def encode(c):
        return {'id':c.uid,'start':rational(c.start),**({'name':c.name} if c.name else {}),
                      'pieces':ranges(c.pieces),
                      'left_reserve':ranges(c.left_reserve),
                      'right_reserve':ranges(c.right_reserve),
                      'fades':{key:getattr(c.fades,key) for key in Fades.__dataclass_fields__},
                      **({'components':[encode(child) for child in c.components]} if c.components else {})}
    return {'origin':rational(model.origin),'extent':rational(model.extent),'clips':[encode(c) for c in model.clips]}


def source_info(path):
    stat = Path(path).stat()
    return {'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}


def document(model,source,canvas=None):
    path = str(Path(source).resolve())
    sources = getattr(model,'sources',())
    lanes = (model.video,model.audio) if hasattr(model,'video') else (model,)
    compound = any(c.components for lane in lanes for c in lane.clips)
    if sources and (len(sources)>1 or not sources[0].has_video):
        return {'format':'splicelet','version':4 if compound else 3,
                'sources':[{'id':f'source-{i+1}','path':s.path,**source_info(s.path)} for i,s in enumerate(sources)],
                'canvas':canvas,'timeline':timeline(model)}
    return {'format':'splicelet','version':4 if compound else 2 if hasattr(model,'video') else 1,
            'sources':[{'id':'source-1','path':path,**source_info(path)}],
            'timeline':timeline(model)}


def read(path):
    with Path(path).open(encoding='utf-8') as stream:
        data = json.load(stream)
    if not isinstance(data,dict): raise ValueError('Invalid project document.')
    if data.get('format')!='splicelet' or type(data.get('version')) is not int or data['version'] not in (1,2,3,4):
        raise ValueError('Unsupported Splicelet project format or version.')
    validate_sources(data)
    if data['version']==3 or 'canvas' in data:
        canvas = data.get('canvas')
        if not isinstance(canvas,dict) or any(type(canvas.get(k)) is not int or not 1<=canvas[k]<=32768 for k in ('width','height')):
            raise ValueError('Invalid project canvas.')
    return data


def validate_sources(data):
    sources = data['sources']
    if not isinstance(sources,list) or not sources:
        raise ValueError('The project has no imported sources.')
    for source in sources:
        if not isinstance(source,dict) or not isinstance(source.get('path'),str): raise ValueError('Invalid imported source reference.')
        source_file = Path(source['path'])
        if not source_file.is_absolute(): raise ValueError('Imported source must use a full path.')
        if not source_file.is_file(): raise ValueError(f'Imported source not found:\n{source_file}')
        if source_info(source_file)!={key:source[key] for key in ('size','mtime_ns')}:
            raise ValueError(f'Imported source has changed:\n{source_file}')
    if [s.get('id') for s in sources]!=[f'source-{i+1}' for i in range(len(sources))]:
        raise ValueError('Invalid source IDs.')
    if data.get('version',2)<3 and (len(sources)!=1 or sources[0]['id']!='source-1'):
        raise ValueError('This version supports projects with one imported video only.')


def restore(data,times,duration,sources=()):
    if data.get('version') in (2,3,4) and 'video' in data['timeline']:
        from .tracks import Tracks
        state = data['timeline']
        video = restore({'timeline':state['video']},times,duration,sources)
        audio = restore({'timeline':state['audio']},times,duration,sources)
        linked = state['linked']
        if type(linked) is not bool: raise ValueError('Invalid audio/video link mode.')
        if video.origin!=audio.origin or video.extent!=audio.extent or (linked and video.clips!=audio.clips):
            raise ValueError('Invalid linked lanes or project bounds.')
        audio.selected_ids.clear(); audio.selection_anchor = None
        return Tracks(video,audio,linked)
    model = Clips(len(times),times,duration)
    model.sources = sources
    state = data['timeline']
    model.origin,model.extent = fraction(state['origin']),fraction(state['extent'])
    if model.extent<model.origin: raise ValueError('Invalid project duration.')
    def ranges(items,required=False):
        if not isinstance(items,list) or (required and not items): raise ValueError('Invalid source ranges.')
        result = []
        for item in items:
            a,b = item['first'],item['end']
            source = next((s for i,s in enumerate(sources) if item['source']==f'source-{i+1}'),None)
            count = source.end-source.first if source else len(times)
            if (source is None and item['source']!='source-1') or type(a) is not int or type(b) is not int or not 0<=a<b<=count:
                raise ValueError('Invalid source frame range.')
            if source: a,b = a+source.first,b+source.first
            result.append((a,b))
        return tuple(result)
    clips = []
    ids = set()
    cursor = model.origin
    def decode(item,component=False):
        uid = item['id']
        if type(uid) is not int or uid<0 or (not component and uid in ids): raise ValueError('Invalid clip ID.')
        if not component: ids.add(uid)
        values = item['fades']
        if set(values)!=set(Fades.__dataclass_fields__) or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values.values()):
            raise ValueError('Invalid clip fades.')
        name = item.get('name','')
        if not isinstance(name,str) or len(name)>120 or any(ord(c)<32 or ord(c)==127 for c in name):
            raise ValueError('Invalid clip name.')
        clip = Clip(uid,fraction(item['start']),ranges(item['pieces'],True),Fades(**values),
                    ranges(item['left_reserve']),ranges(item['right_reserve']),name)
        if 'components' in item:
            items = item['components']
            if component or not isinstance(items,list) or not items: raise ValueError('Invalid compound clip.')
            children = tuple(decode(child,True) for child in items)
            if (children[0].start!=0 or any(b.start<=a.start or b.start>model.end(a)+Fraction(1,1000000) for a,b in zip(children,children[1:]))
                    or not model.valid_overlaps([Clip(0,model.origin+c.start,c.pieces,c.fades) for c in children])):
                raise ValueError('Invalid compound clip positions.')
            expected = model.compound(clip,children)
            if (clip.pieces,clip.fades,clip.left_reserve,clip.right_reserve)!=(expected.pieces,expected.fades,expected.left_reserve,expected.right_reserve):
                raise ValueError('Inconsistent compound clip metadata.')
            clip = Clip(clip.uid,clip.start,clip.pieces,clip.fades,clip.left_reserve,clip.right_reserve,clip.name,children)
        return clip
    for item in state['clips']:
        clip = decode(item)
        if clip.start<model.origin or clip.start<cursor or model.end(clip)>model.extent: raise ValueError('Invalid clip position.')
        clips.append(clip)
        cursor = clip.start
    if not model.valid_overlaps(clips): raise ValueError('Invalid nested or triple clip overlap.')
    model.clips = clips
    model.selected_ids = {clips[0].uid} if clips else set()
    model.selection_anchor = clips[0].uid if clips else None
    model.next_id = max(ids,default=-1)+1
    return model


def write(path,data):
    destination = Path(path).resolve()
    for source in data['sources']:
        source_file = Path(source['path'])
        if destination==source_file.resolve() or (destination.exists() and os.path.samefile(destination,source_file)):
            raise ValueError('A project cannot replace an imported source or a source alias.')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=destination.parent,
                                         prefix='.splicelet-',suffix='.tmp',delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data,stream,indent=2,allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,destination)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
