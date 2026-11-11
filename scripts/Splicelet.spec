# Build from the project-local Conda runtime with scripts/build-portable.ps1.
from pathlib import Path
import json
import runpy
import sys
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
    VarFileInfo, VarStruct,
)

root = Path(SPECPATH).parent
runtime = Path(sys.prefix)
version = runpy.run_path(str(root/'splicelet'/'__init__.py'))['__version__']
build_helpers = runpy.run_path(str(root/'splicelet'/'build_info.py'))
build_info = build_helpers['git_build_info'](root)
display_version = build_helpers['version_label'](version,build_info)
build_info_path = root/'artifacts'/'pyinstaller'/'_build_info.json'
build_info_path.parent.mkdir(parents=True,exist_ok=True)
build_info_path.write_text(json.dumps(build_info,indent=2)+'\n',encoding='utf-8')
windows_version = (*map(int,version.split('.')),0)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=windows_version,prodvers=windows_version,
                      mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),
    kids=[
        StringFileInfo([StringTable('040904B0',[
            StringStruct('FileDescription','Splicelet video editor'),
            StringStruct('FileVersion',display_version),
            StringStruct('InternalName','Splicelet'),
            StringStruct('OriginalFilename','Splicelet.exe'),
            StringStruct('ProductName','Splicelet'),
            StringStruct('ProductVersion',display_version),
        ])]),
        VarFileInfo([VarStruct('Translation',[1033,1200])]),
    ],
)
qml = [(str(path),'splicelet') for path in (root/'splicelet').glob('*.qml')]

a = Analysis(
    [str(root/'scripts'/'portable_entry.py')],
    pathex=[str(root)],
    binaries=[(str(runtime/'Library'/'bin'/'ffmpeg.exe'),'ffmpeg')],
    datas=qml+[(str(root/'artifacts'/'icon'/'splicelet.png'),'splicelet/assets'),
               (str(build_info_path),'splicelet')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,a.scripts,[],exclude_binaries=True,name='Splicelet',
    debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
    console=False,icon=str(root/'artifacts'/'icon'/'splicelet.ico'),
    version=version_info,
)
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Splicelet')
