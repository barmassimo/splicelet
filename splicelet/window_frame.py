"""Windows hit testing for the interactive, expanded QML title bar."""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtQuick import QQuickItem


class WindowFrame(QAbstractNativeEventFilter):
    """Let Windows handle caption gestures, and QML handle menu clicks.

    Qt's expanded-area helper window otherwise forwards caption clicks as
    synthetic presses/releases, losing double-clicks and interfering with menus.
    """

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.handle = int(window.winId())
        self.bar = window.findChild(QQuickItem, 'windowTitleBar')
        self.menu = window.findChild(QQuickItem, 'applicationMenu')
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.user32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
        self.user32.IsChild.restype = wintypes.BOOL
        self.user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message != 0x0084 or not self.bar.isVisible():  # WM_NCHITTEST
            return False, 0
        hwnd = int(msg.hWnd)
        if hwnd != self.handle and not self.user32.IsChild(self.handle, hwnd):
            return False, 0
        origin = wintypes.POINT(0, 0)
        rect = wintypes.RECT()
        self.user32.ClientToScreen(self.handle, ctypes.byref(origin))
        self.user32.GetClientRect(self.handle, ctypes.byref(rect))
        scale = self.window.devicePixelRatio()
        x = (ctypes.c_short(msg.lParam & 0xffff).value-origin.x)/scale
        y = (ctypes.c_short((msg.lParam >> 16) & 0xffff).value-origin.y)/scale
        # Keep the OS/Qt caption buttons and resize borders intact.
        right = max(150, self.window.safeAreaMargins().right())
        if not (0 <= y < self.bar.height() and 8 <= x < rect.right/scale-right):
            return False, 0
        if hwnd != self.handle:
            # Skip Qt's overlapping helper child so the parent gets real input.
            return True, -1  # HTTRANSPARENT
        if y < 8 and self.window.visibility() != self.window.Visibility.Maximized:
            return False, 0
        if x < 36:
            return True, 3  # HTSYSMENU: native menu and double-click close
        menu_end = self.menu.x()+self.menu.width() if self.menu.property('opened') else self.menu.x()
        return True, 1 if x < menu_end else 2  # HTCLIENT / HTCAPTION
