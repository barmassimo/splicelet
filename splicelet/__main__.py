import argparse
import os
from pathlib import Path
import sys
from . import __version__

parser = argparse.ArgumentParser(description='Splicelet local video editor')
parser.add_argument('--version', action='version', version=f'Splicelet {__version__}')
parser.add_argument('file', nargs='?')
parser.add_argument('--smoke-test', action='store_true')
parser.add_argument('--muted', action='store_true')
args = parser.parse_args()
if args.smoke_test:
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    os.environ.setdefault('QT_QUICK_BACKEND','software')

from PySide6.QtCore import QTimer, QUrl, QLocale
from PySide6.QtGui import QGuiApplication, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from .controller import FrameProvider, Preview, FrameKeys

QLocale.setDefault(QLocale('en_US'))
if sys.platform == 'win32':
    import ctypes
    # Give the Windows taskbar a stable identity before creating any windows.
    ctypes.OleDLL('shell32').SetCurrentProcessExplicitAppUserModelID('Splicelet.Splicelet')
app = QGuiApplication(sys.argv)
QQuickStyle.setStyle('Basic')
# Windows' offscreen platform may expose no system fonts. Register the same
# local fonts explicitly so visual tests exercise readable text as well.
if sys.platform == 'win32' and not QFontDatabase.families():
    font_dir = Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'
    for font_name in ('segoeui.ttf','segoeuib.ttf','consola.ttf'):
        if (font_dir/font_name).exists():
            QFontDatabase.addApplicationFont(str(font_dir/font_name))
app.setApplicationName('Splicelet')
app.setApplicationVersion(__version__)
app.setOrganizationName('Splicelet')
icon = Path(__file__).with_name('assets')/('splicelet.png' if getattr(sys,'frozen',False) else 'splicelet.svg')
app.setWindowIcon(QIcon(str(icon)))
provider = FrameProvider()
preview = Preview(provider,muted=args.muted or args.smoke_test)
engine = QQmlApplicationEngine()
engine.addImageProvider('frames',provider)
engine.setInitialProperties({'preview':preview,'applicationIconSource':QUrl.fromLocalFile(str(icon))})
engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('Main.qml'))))
if not engine.rootObjects():
    preview.close()
    sys.exit(1)
if sys.platform == 'win32' and app.platformName() == 'windows':
    from .window_frame import WindowFrame
    window_frame = WindowFrame(engine.rootObjects()[0])
    app.installNativeEventFilter(window_frame)
frame_keys = FrameKeys(engine.rootObjects()[0],preview)
app.installEventFilter(frame_keys)
app.aboutToQuit.connect(preview.close)
if args.file:
    QTimer.singleShot(0,lambda:preview.openProject(QUrl.fromLocalFile(str(Path(args.file).resolve()))) if Path(args.file).suffix.lower()=='.splicelet' else preview.open_path(args.file))
if args.smoke_test:
    from .smoke import SmokeTest
    smoke = SmokeTest(app,engine.rootObjects()[0],preview)
sys.exit(app.exec())
