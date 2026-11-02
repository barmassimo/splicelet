"""Verify appearance preferences and collapsible application menu."""
import json
import os
from pathlib import Path
from test_fixture import ensure_fixture
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT = ROOT/'artifacts/appearance-tests'
OUT.mkdir(parents=True,exist_ok=True)
from PySide6.QtCore import QObject, QMetaObject, QSettings, QUrl, Qt, QPointF, QLocale, QPoint
from PySide6.QtGui import QGuiApplication, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from splicelet.controller import FrameProvider, Preview

QLocale.setDefault(QLocale('en_US'))
app = QGuiApplication([])
QQuickStyle.setStyle('Basic')
if not QFontDatabase.families():
    for name in ('segoeui.ttf','segoeuib.ttf','consola.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name))
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(OUT/'settings'))
provider = FrameProvider(); preview = Preview(provider,muted=True)
engine = QQmlApplicationEngine(); engine.addImageProvider('frames',provider)
warnings = []
engine.warnings.connect(lambda items:warnings.extend(str(item) for item in items))
engine.setInitialProperties({'preview':preview})
engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
assert engine.rootObjects()
window = engine.rootObjects()[0]
checks = []
def passed(name):
    checks.append(name)
    print('PASS',name,flush=True)
def wait(predicate):
    deadline = time.monotonic()+30
    while not predicate():
        assert time.monotonic()<deadline,preview.status
        app.processEvents(); QTest.qWait(10)
def item_named(name,item=None):
    item=window.contentItem() if item is None else item
    if item.objectName()==name: return item
    for child in item.childItems():
        found=item_named(name,child)
        if found is not None: return found
    return None
try:
    preview.setDarkTheme(False)
    QTest.qWait(100)
    status_text=window.findChild(QQuickItem,'statusText')
    time_input=window.findChild(QQuickItem,'timeInput')
    assert status_text.property('text')=='Ready'
    assert abs(status_text.mapToScene(QPointF()).x()-time_input.mapToScene(QPointF()).x())<1
    window.grabWindow().save(str(OUT/'light-ready-status.png'))
    preview.open_path(str(ensure_fixture()))
    wait(lambda:preview.indexedReady and not preview.busy)
    QTest.qWait(150)
    menu=window.findChild(QQuickItem,'applicationMenu')
    button=window.findChild(QQuickItem,'menuButton')
    view=window.findChild(QObject,'viewMenu')
    action=window.findChild(QObject,'darkThemeAction')
    snapshot=preview._clips.snapshot()
    generation=preview._generation
    window.grabWindow().save(str(OUT/'light.png'))
    navigation=window.findChild(QQuickItem,'sidePanelTabs')
    source_tab=window.findChild(QQuickItem,'sourceTab')
    properties_tab=window.findChild(QQuickItem,'propertiesTab')
    assert source_tab.property('text')=='Sources'
    def click_item(item):
        QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,
                         item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint())
        QTest.qWait(80)
    assert source_tab.mapToScene(QPointF()).x()>properties_tab.mapToScene(QPointF()).x()
    assert source_tab.mapToScene(QPointF()).y()==properties_tab.mapToScene(QPointF()).y()
    image=window.findChild(QQuickItem,'previewImage')
    assert navigation.mapToScene(QPointF()).x()<image.mapToScene(QPointF()).x()
    click_item(source_tab)
    assert navigation.property('currentIndex')==1
    window.grabWindow().save(str(OUT/'light-source.png'))
    click_item(properties_tab)
    assert navigation.property('currentIndex')==0
    preview.selectClip(0,False,False)
    assert preview.selectedClipName=='Clip 1'
    assert Path(preview.suggestedExportUrl.toLocalFile()).stem.endswith('_clip-1')
    assert window.findChild(QQuickItem,'clipName').property('text')=='Clip 1'
    QTest.qWait(100)
    window.grabWindow().save(str(OUT/'light-properties.png'))
    timeline=window.findChild(QQuickItem,'editTimeline')
    time_input=window.findChild(QQuickItem,'timeInput')
    inset=timeline.property('inset')
    assert abs(time_input.mapToScene(QPointF()).x()-timeline.mapToScene(QPointF(inset,0)).x())<1
    status_row=window.findChild(QQuickItem,'statusRow')
    assert abs(status_row.mapToScene(QPointF()).x()-time_input.mapToScene(QPointF()).x())<1
    assert abs(status_row.mapToScene(QPointF(status_row.width(),0)).x()-timeline.mapToScene(QPointF(timeline.width()-inset,0)).x())<1
    compact_height=timeline.height()
    timeline.setProperty('viewDuration',30); QTest.qWait(80)
    scrollbar=window.findChild(QQuickItem,'timelineScrollBar')
    assert scrollbar.isVisible() and timeline.height()>compact_height
    assert scrollbar.mapToScene(QPointF(0,scrollbar.height())).y()<time_input.mapToScene(QPointF()).y()
    window.grabWindow().save(str(OUT/'light-compact-zoom.png'))
    timeline.setProperty('viewDuration',0); QTest.qWait(80)
    preview.selectClip(0,True)
    snapshot=preview._clips.snapshot()
    passed('horizontal_panel_navigation_switches_pages')
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,
                     button.mapToScene(QPointF(button.width()/2,button.height()/2)).toPoint())
    QTest.qWait(80)
    assert menu.property('opened')
    click_item(item_named('panelMenuSection2'))
    window.grabWindow().save(str(OUT/'light-menu.png'))
    click_item(item_named('panelCommand_darkThemeAction'))
    assert preview.darkTheme and action.property('checked') and not menu.property('opened')
    assert window.property('color').name()=='#171c24'
    window.grabWindow().save(str(OUT/'dark.png'))
    restored=Preview(FrameProvider(),muted=True)
    assert restored.darkTheme
    restored.close()
    assert preview._clips.snapshot()==snapshot and preview._generation==generation
    passed('night_theme_action_repaints_and_persists_without_changing_source_state')
    QTest.keyClick(window,Qt.Key.Key_M,Qt.KeyboardModifier.ControlModifier); QTest.qWait(50)
    assert menu.property('opened')
    click_item(item_named('panelMenuSection0'))
    window.grabWindow().save(str(OUT/'dark-menu.png'))
    QTest.keyClick(window,Qt.Key.Key_Escape); QTest.qWait(30)
    QTest.keyClick(window,Qt.Key.Key_Escape); QTest.qWait(30)
    assert not menu.property('opened')
    # Menu dismisses back to the page active before opening; tab clicks also dismiss.
    click_item(source_tab)
    click_item(button)
    click_item(button)
    assert navigation.property('currentIndex')==1 and not menu.property('opened')
    click_item(button)
    click_item(properties_tab)
    assert navigation.property('currentIndex')==0 and not menu.property('opened')
    passed('menu_restores_previous_page_and_tabs_dismiss_it')
    QTest.keyClick(window,Qt.Key.Key_M,Qt.KeyboardModifier.ControlModifier); QTest.qWait(30)
    assert menu.property('opened')
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(600,300))
    assert not menu.property('opened')
    passed('menu_button_shortcut_escape_and_outside_click')
    window.setWidth(760); window.setHeight(560); QTest.qWait(100)
    assert timeline.mapToScene(QPointF(timeline.width(),0)).x()<=window.width()-12
    window.grabWindow().save(str(OUT/'dark-minimum.png'))
    click_item(button)
    window.grabWindow().save(str(OUT/'dark-minimum-menu.png'))
    QTest.keyClick(window,Qt.Key.Key_Escape); QTest.qWait(30)
    QMetaObject.invokeMethod(window.findChild(QObject,'aboutDialog'),'open'); QTest.qWait(80)
    window.grabWindow().save(str(OUT/'dark-dialog.png'))
    QMetaObject.invokeMethod(window.findChild(QObject,'aboutDialog'),'accept')
    preview.setDarkTheme(False)
    restored=Preview(FrameProvider(),muted=True)
    assert not restored.darkTheme
    restored.close()
    passed('minimum_layout_dark_dialog_and_light_preference_restore')
    window.setWidth(1120); window.setHeight(790); QTest.qWait(80)
    preview.selectClip(0)
    preview.renameSelected('Menu command test')
    assert preview.canUndo
    click_item(button)
    click_item(item_named('panelMenuSection1'))
    click_item(item_named('panelCommand_undoAction'))
    assert not menu.property('opened') and preview.canRedo
    recent_path=OUT/f'menu-recent-{time.time_ns()}.splicelet'
    assert preview.saveProjectAs(QUrl.fromLocalFile(str(recent_path)))
    click_item(button)
    click_item(item_named('panelMenuSection0'))
    recent_button=item_named('panelRecentProjects')
    wait(lambda:recent_button.isEnabled())
    click_item(recent_button)
    window.grabWindow().save(str(OUT/'light-menu-recent.png'))
    click_item(item_named('panelRecentProject0'))
    wait(lambda:not preview.busy and not preview.openingProject)
    assert not menu.property('opened') and preview.projectName==recent_path.stem
    passed('inline_undo_and_recent_project_commands_share_existing_actions')
    click_item(button)
    panel_menu=window.findChild(QQuickItem,'panelApplicationMenu')
    assert panel_menu.property('section')==-1
    click_item(item_named('panelMenuSection0'))
    assert not item_named('panelRecentProjects').property('expanded')
    click_item(item_named('panelRecentProjects'))
    click_item(button)
    click_item(button)
    assert panel_menu.property('section')==-1
    click_item(item_named('panelMenuSection0'))
    assert not item_named('panelRecentProjects').property('expanded')
    QTest.keyClick(window,Qt.Key.Key_Escape); QTest.qWait(30)
    QTest.keyClick(window,Qt.Key.Key_M,Qt.KeyboardModifier.ControlModifier); QTest.qWait(30)
    assert panel_menu.property('section')==-1
    window.grabWindow().save(str(OUT/'light-menu-collapsed.png'))
    passed('every_menu_open_collapses_sections_and_recent_projects')
    assert not [warning for warning in warnings if 'PanelMenu.qml:' in warning],warnings
    passed('panel_menu_initialization_and_recent_commands_emit_no_qml_warnings')
finally:
    preview.close()
    engine.deleteLater()
(OUT/'report.json').write_text(json.dumps({'status':'pass','checks':checks,'warnings':warnings},indent=2),encoding='utf-8')
