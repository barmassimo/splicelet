import QtQuick
import QtQuick.Controls

Item {
    id: root
    required property var preview
    required property var theme
    implicitWidth: 166
    implicitHeight: 30
    objectName: "audioMeter"
    readonly property bool quiet: preview.muted || preview.volume===0 || !preview.audioEnabled
    Accessible.role: Accessible.Indicator
    Accessible.name: "Stereo audio level before listening volume"

    Column {
        anchors.left: parent.left; anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 1
        Repeater {
            model: 2
            delegate: Item {
                required property int index
                width: root.width; height: 9
                Label { text: index===0 ? "L" : "R"; color: theme.muted; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                Rectangle {
                    id: track
                    x: 15; width: parent.width-x; height: 6
                    anchors.verticalCenter: parent.verticalCenter
                    radius: 1; color: theme.line
                    readonly property real level: Math.max(0,Math.min(1,(preview.audioLevels[index]+60)/60))
                    readonly property real peak: Math.max(0,Math.min(1,(preview.audioPeaks[index]+60)/60))
                    Item {
                        width: track.width*track.level; height: parent.height; clip: true
                        Rectangle {
                            width: track.width; height: parent.height
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: root.quiet ? theme.disabled : theme.meterGreen }
                                GradientStop { position: .8; color: root.quiet ? theme.disabled : theme.meterGreen }
                                GradientStop { position: .8001; color: root.quiet ? theme.disabled : theme.meterYellow }
                                GradientStop { position: .95; color: root.quiet ? theme.disabled : theme.meterYellow }
                                GradientStop { position: .9501; color: root.quiet ? theme.disabled : theme.meterRed }
                                GradientStop { position: 1; color: root.quiet ? theme.disabled : theme.meterRed }
                            }
                        }
                    }
                    Rectangle { visible: track.peak>0; x: Math.min(parent.width-width,parent.width*track.peak); width: 2; height: parent.height; color: root.quiet ? theme.muted : theme.text }
                }
            }
        }
        Item {
            x: 15; width: root.width-x; height: 10
            Repeater {
                model: [{v:-60,t:"−60"},{v:-24,t:"−24"},{v:-12,t:"−12"},{v:0,t:"0"}]
                delegate: Label {
                    required property var modelData
                    text: modelData.t; color: theme.muted; font.pixelSize: 9
                    x: Math.max(0,Math.min(parent.width-width,parent.width*(modelData.v+60)/60-width/2))
                }
            }
        }
    }
    HoverHandler { id: hover }
    ToolTip.visible: hover.hovered
    ToolTip.text: "Stereo sample peaks · dBFS\nBefore listening volume; export normalization is not included."
}
