"""Immutable source catalog and exact virtual source coordinates, independent of Qt."""
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class Source:
    path: str
    first: int
    end: int
    offset: Fraction
    duration: Fraction
    origin: float
    time_base: Fraction
    pts: tuple
    has_video: bool
    audio_timeline: dict | None
    width: int = 640
    height: int = 360
    fps: float = 30.
    aspect: Fraction = Fraction(1)
    rotation: int = 0

    @property
    def virtual_origin(self): return self.origin-float(self.offset)


def catalog_entry(path, metadata, index, previous=()):
    base = Fraction(index['time_base'])
    origin = metadata['origin']
    local = tuple(p*base-Fraction(str(origin)) for p in index['pts'])
    duration = Fraction(str(metadata['duration']))-Fraction(str(origin))
    if not local or duration<=local[-1]:
        raise ValueError('The source duration does not cover its timestamp index.')
    first = previous[-1].end if previous else 0
    offset = previous[-1].offset+previous[-1].duration-local[0] if previous else Fraction(0)
    source = Source(path,first,first+len(local),offset,duration,origin,base,tuple(index['pts']),
                    metadata.get('has_video',True),metadata['audio_timeline'],metadata['width'],
                    metadata['height'],metadata['fps'],Fraction(metadata.get('aspect','1')),
                    metadata.get('rotation',0))
    return source,tuple(t+offset for t in local)


def source_for(sources,frame):
    return next(s for s in sources if s.first<=frame<s.end)


def fit_geometry(source,width,height):
    """Fit display aspect into the fixed canvas, using square output pixels."""
    sw,sh = source.width*float(source.aspect),source.height
    if source.rotation in (90,270): sw,sh = sh,sw
    scale = min(width/sw,height/sh)
    w,h = max(1,round(sw*scale)),max(1,round(sh*scale))
    return w,h,(width-w)//2,(height-h)//2
