"""Render the vector app mark to PNG and a multi-resolution Windows ICO."""
from pathlib import Path
import struct

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


root = Path(__file__).resolve().parents[1]
out = root/'artifacts'/'icon'
out.mkdir(parents=True,exist_ok=True)
renderer = QSvgRenderer(str(root/'splicelet'/'assets'/'splicelet.svg'))
if not renderer.isValid(): raise RuntimeError('Invalid app icon SVG.')
sizes = (16,20,24,32,40,48,64,128,256)
frames = []
for size in sizes:
    image = QImage(size,size,QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer,'PNG'): raise RuntimeError('Could not encode the app icon.')
    frames.append(bytes(data))
    if size==256:
        if not image.save(str(out/'splicelet.png')): raise RuntimeError('Could not save the app icon.')

offset = 6+16*len(sizes)
directory = bytearray(struct.pack('<HHH',0,1,len(sizes)))
for size,data in zip(sizes,frames):
    directory.extend(struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(data),offset))
    offset += len(data)
(out/'splicelet.ico').write_bytes(directory+b''.join(frames))
print(f'App icon: {out / "splicelet.ico"}')
