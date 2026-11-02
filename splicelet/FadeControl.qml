import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    readonly property var theme: ApplicationWindow.window.uiTheme
    id: control
    required property string title
    required property string fieldName
    required property real value
    signal committed(string text)
    readonly property bool editing: field.activeFocus
    spacing: 0
    function finishEditing() {
        if (field.activeFocus) {
            committed(field.text)
            field.focus = false
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Label { text: control.title; color: theme.text; font.pixelSize: 12; Layout.fillWidth: true }
        TextField {
            id: field
            objectName: control.fieldName
            Layout.preferredWidth: 75
            implicitHeight: 26
            font.pixelSize: 12
            horizontalAlignment: Text.AlignRight
            selectByMouse: true
            Accessible.name: control.fieldName
            background: Rectangle {
                radius: 6; color: theme.window
                border.width: field.activeFocus ? 1 : 0
                border.color: theme.accent
            }
            onEditingFinished: control.committed(text)
            onAccepted: focus = false
            Binding {
                target: field; property: "text"; when: !field.activeFocus
                value: String(slider.pressed ? Math.round(slider.value*100)/100 : control.value)
                restoreMode: Binding.RestoreNone
            }
        }
        Label { text: "s"; color: theme.muted; font.pixelSize: 11 }
    }
    Slider {
        id: slider
        objectName: control.fieldName+"Slider"
        Layout.fillWidth: true
        from: 0; to: 4; stepSize: 0.01
        implicitHeight: 22
        focusPolicy: Qt.NoFocus
        onPressedChanged: {
            if (pressed) field.focus = false
            else control.committed(value.toFixed(2))
        }
        Binding { target: slider; property: "value"; value: Math.max(0,Math.min(4,control.value)); when: !slider.pressed; restoreMode: Binding.RestoreNone }
        background: Rectangle {
            x: slider.leftPadding
            y: slider.topPadding+(slider.availableHeight-height)/2
            width: slider.availableWidth; height: 4; radius: 2; color: theme.track
            Rectangle { width: slider.visualPosition*parent.width; height: parent.height; radius: 2; color: theme.accent }
        }
        handle: Rectangle {
            x: slider.leftPadding+slider.visualPosition*(slider.availableWidth-width)
            y: slider.topPadding+(slider.availableHeight-height)/2
            width: 14; height: 14; radius: 7
            color: theme.surface; border.color: theme.accent
        }
    }
}
