import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    readonly property var theme: ApplicationWindow.window.uiTheme
    id: properties
    required property var preview
    objectName: "clipProperties"
    implicitWidth: 260
    color: theme.surface
    radius: 12
    readonly property bool editing: clipName.activeFocus || audioIn.editing || audioOut.editing || videoIn.editing || videoOut.editing
    function finishEditing() {
        clipName.finishEditing(); audioIn.finishEditing(); audioOut.finishEditing(); videoIn.finishEditing(); videoOut.finishEditing()
    }
    ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.margins: 12
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            width: scroll.availableWidth
            spacing: 6
            Label { text: "Clip properties"; font.pixelSize: 15; font.weight: Font.DemiBold; color: theme.text }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                TextField {
                    id: clipName
                    objectName: "clipName"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 40
                    implicitHeight: 28
                    font.pixelSize: 12
                    maximumLength: 120
                    selectByMouse: true
                    focusPolicy: Qt.StrongFocus
                    Accessible.name: "Clip name"
                    background: Rectangle {
                        radius: 6; color: theme.window
                        border.width: clipName.activeFocus ? 1 : 0
                        border.color: theme.accent
                    }
                    property bool modified: false
                    function finishEditing() {
                        if (modified) { modified=false; preview.renameSelected(text) }
                        focus=false
                    }
                    onTextEdited: modified=true
                    onEditingFinished: finishEditing()
                    onAccepted: finishEditing()
                    Binding { target: clipName; property: "text"; value: preview.selectedClipName; when: !clipName.activeFocus; restoreMode: Binding.RestoreNone }
                }
                Label { objectName: "clipDuration"; text: preview.selectedDurationText; color: theme.muted; font.family: "Consolas"; font.pixelSize: 11 }
            }
            Label { visible: preview.showVideoFades; text: "Video"; font.weight: Font.DemiBold; color: theme.text; Layout.topMargin: 6 }
            FadeControl {
                id: videoIn
                visible: preview.showVideoFades
                Layout.fillWidth: true
                title: "Fade in"; fieldName: "videoFadeIn"
                value: preview.fadeValues.video_in
                onCommitted: function(text) { preview.setFade("video_in",text) }
            }
            FadeControl {
                id: videoOut
                visible: preview.showVideoFades
                Layout.fillWidth: true
                title: "Fade out"; fieldName: "videoFadeOut"
                value: preview.fadeValues.video_out
                onCommitted: function(text) { preview.setFade("video_out",text) }
            }
            Label { visible: preview.showAudioFades; text: "Audio"; font.weight: Font.DemiBold; color: theme.text; Layout.topMargin: 6 }
            FadeControl {
                id: audioIn
                visible: preview.showAudioFades
                Layout.fillWidth: true
                title: "Fade in"; fieldName: "audioFadeIn"
                value: preview.fadeValues.audio_in
                enabled: preview.hasAudio
                onCommitted: function(text) { preview.setFade("audio_in",text) }
            }
            FadeControl {
                id: audioOut
                visible: preview.showAudioFades
                Layout.fillWidth: true
                title: "Fade out"; fieldName: "audioFadeOut"
                value: preview.fadeValues.audio_out
                enabled: preview.hasAudio
                onCommitted: function(text) { preview.setFade("audio_out",text) }
            }
            Label {
                text: "0 disables the fade.\nSliders: 0–4 s in 0.01 s steps. You can type other durations."
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                font.pixelSize: 11
                color: theme.muted
            }
        }
    }
}
