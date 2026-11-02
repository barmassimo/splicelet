import QtQuick
import QtQuick.Controls

Button {
    readonly property var theme: ApplicationWindow.window ? ApplicationWindow.window.uiTheme : unattachedTheme
    Theme { id: unattachedTheme; dark: false }
    id: control
    implicitWidth: Math.max(42, contentItem.implicitWidth + 24)
    implicitHeight: 36
    padding: 10
    contentItem: Text {
        text: control.text
        font: control.font
        color: !control.enabled ? theme.disabledText : control.highlighted ? "#ffffff" : theme.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 8
        color: !control.enabled ? theme.well : control.highlighted
               ? (control.down ? "#194e82" : control.hovered ? "#1e5f9d" : theme.accent)
               : (control.down ? theme.pressed : control.hovered ? theme.hover : theme.surface)
        border.width: control.visualFocus ? 2 : 0
        border.color: control.visualFocus ? theme.accent : theme.buttonBorder
    }
}
