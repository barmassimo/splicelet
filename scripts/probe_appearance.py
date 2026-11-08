"""Verify appearance preferences and title-bar application menu."""
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
if app.platformName()=='windows':
    from splicelet.window_frame import WindowFrame
    window_frame=WindowFrame(window)
    app.installNativeEventFilter(window_frame)
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
    drag_area=window.findChild(QQuickItem,'titleBarDragArea')
    def double_click_title():
        point=drag_area.mapToScene(QPointF(drag_area.width()/2,drag_area.height()/2)).toPoint()
        QTest.mouseDClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
        QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
        QTest.qWait(200)
    double_click_title()
    assert window.visibility()==window.Visibility.Maximized,window.visibility()
    double_click_title()
    assert window.visibility()==window.Visibility.Windowed,window.visibility()
    passed('title_bar_double_click_maximizes_and_restores')
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
    icon=window.findChild(QQuickItem,'systemMenuIcon')
    assert icon.mapToScene(QPointF(icon.width(),0)).x()<button.mapToScene(QPointF()).x()
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
    click_item(item_named('menuCategoryView'))
    window.grabWindow().save(str(OUT/'light-menu.png'))
    click_item(item_named('menuCommand_darkThemeAction'))
    assert preview.darkTheme and action.property('checked') and not menu.property('opened')
    assert window.property('color').name()=='#171c24'
    window.grabWindow().save(str(OUT/'dark.png'))
    restored=Preview(FrameProvider(),muted=True)
    assert restored.darkTheme
    restored.close()
    assert preview._clips.snapshot()==snapshot and preview._generation==generation
    passed('night_theme_action_repaints_and_persists_without_changing_source_state')
    for width,height in ((1120,790),(760,560)):
        window.setWidth(width); window.setHeight(height); QTest.qWait(80)
        before=image.mapToScene(QPointF())
        click_item(button)
        assert menu.property('opened')
        assert not window.findChild(QQuickItem,'windowTitleLabel').isVisible()
        assert button.mapToScene(QPointF()).y()<navigation.mapToScene(QPointF()).y()
        assert image.mapToScene(QPointF())==before
        categories=[item_named('menuCategory'+name) for name in ('File','Edit','View','Help')]
        center_y=button.mapToScene(QPointF(0,button.height()/2)).y()
        assert all(abs(item.mapToScene(QPointF(0,item.height()/2)).y()-center_y)<1 for item in categories)
        assert categories[0].mapToScene(QPointF()).x()>=button.mapToScene(QPointF(button.width(),0)).x()
        assert categories[-1].mapToScene(QPointF(categories[-1].width(),0)).x()<width-150
        click_item(categories[0])
        window.grabWindow().save(str(OUT/f'dark-menu-{width}.png'))
        QTest.keyClick(window,Qt.Key.Key_Escape); QTest.qWait(30)
        QTest.keyClick(window,Qt.Key.Key_Escape); QTest.qWait(30)
        assert not menu.property('opened')
        assert window.findChild(QQuickItem,'windowTitleLabel').isVisible()
    passed('horizontal_title_bar_menu_preserves_workspace_at_both_window_sizes')
    click_item(source_tab)
    click_item(button)
    click_item(button)
    assert navigation.property('currentIndex')==1 and not menu.property('opened')
    click_item(button)
    click_item(properties_tab)
    assert navigation.property('currentIndex')==0 and not menu.property('opened')
    QTest.keyClick(window,Qt.Key.Key_M,Qt.KeyboardModifier.ControlModifier); QTest.qWait(30)
    assert menu.property('opened')
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(600,300))
    assert not menu.property('opened')
    passed('menu_button_shortcut_escape_and_outside_click')
    bar=window.findChild(QQuickItem,'compactMenuBar')
    for name in ('File','Edit','View','Help'):
        click_item(button)
        assert bar.property('currentIndex')==-1
        for category in ('File','Edit','View','Help'):
            assert not item_named('menuCategory'+category).property('highlighted')
            assert not window.findChild(QObject,category.lower()+'Menu').property('opened')
        click_item(item_named('menuCategory'+name))
        assert window.findChild(QObject,name.lower()+'Menu').property('opened')
        QTest.keyClick(window,Qt.Key.Key_Escape); QTest.qWait(30)
        QTest.keyClick(window,Qt.Key.Key_Escape); QTest.qWait(30)
        assert not menu.property('opened')
        QTest.mouseMove(window,QPoint(600,300)); QTest.qWait(30)
    passed('each_category_click_opens_its_menu_and_every_reopen_resets_selection')
    click_item(button)
    for name in ('File','Edit','View','Help','File'):
        category=item_named('menuCategory'+name)
        point=category.mapToScene(QPointF(category.width()/2,category.height()/2)).toPoint()
        QTest.mouseMove(window,point); QTest.qWait(120)
        assert window.findChild(QObject,name.lower()+'Menu').property('opened'),name
        assert all(not window.findChild(QObject,other.lower()+'Menu').property('opened')
                   for other in ('File','Edit','View','Help') if other!=name)
    window.grabWindow().save(str(OUT/'hover-menu.png'))
    QTest.keyClick(window,Qt.Key.Key_Escape); QTest.qWait(30)
    QTest.keyClick(window,Qt.Key.Key_Escape); QTest.qWait(30)
    QTest.mouseMove(window,QPoint(600,300)); QTest.qWait(30)
    click_item(button)
    assert bar.property('currentIndex')==-1
    assert all(not item_named('menuCategory'+name).property('highlighted')
               for name in ('File','Edit','View','Help'))
    click_item(button)
    passed('hover_opens_first_category_switches_menus_and_preserves_reopen_reset')


    window.setWidth(1120); window.setHeight(790); QTest.qWait(80)
    preview.selectClip(0)
    preview.renameSelected('Menu command test')
    click_item(button)
    click_item(item_named('menuCategoryEdit'))
    click_item(item_named('menuCommand_undoAction'))
    assert not menu.property('opened') and preview.canRedo
    recent_path=OUT/f'menu-recent-{time.time_ns()}.splicelet'
    assert preview.saveProjectAs(QUrl.fromLocalFile(str(recent_path)))
    click_item(button)
    click_item(item_named('menuCategoryFile'))
    recent=window.findChild(QObject,'recentMenu')
    QTest.keyClick(window,Qt.Key.Key_Down); QTest.keyClick(window,Qt.Key.Key_Down)
    QTest.keyClick(window,Qt.Key.Key_Right); QTest.qWait(100)
    assert recent.property('opened')
    window.grabWindow().save(str(OUT/'recent-project-submenu.png'))
    click_item(item_named('recentProject0'))
    wait(lambda:not preview.busy and not preview.openingProject)
    assert not menu.property('opened') and preview.projectName==recent_path.stem
    passed('undo_and_cascading_recent_project_commands_share_existing_actions')
    preview.setDarkTheme(False)
    assert not warnings,warnings
    passed('title_bar_menu_emits_no_qml_warnings')
finally:
    preview.close()
    engine.deleteLater()
(OUT/'report.json').write_text(json.dumps({'status':'pass','checks':checks,'warnings':warnings},indent=2),encoding='utf-8')
