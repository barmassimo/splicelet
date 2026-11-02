import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    required property var menus
    property int section: -1
    signal collapseSubmenus()
    function reset() {
        section = -1
        collapseSubmenus()
        scroll.contentItem.contentY = 0
    }
    signal dismissed()
    readonly property var theme: ApplicationWindow.window.uiTheme
    color: theme.surface
    radius: 12

    component Command: Button {
        id: command
        required property var entry
        property bool recentProject: false
        action: entry && entry.action ? entry.action : null
        objectName: action && action.objectName ? "panelCommand_" + action.objectName : ""
        text: entry ? entry.text : ""
        enabled: entry ? entry.enabled : false
        Layout.fillWidth: true
        implicitHeight: contentItem.implicitHeight + 16
        padding: 8
        ToolTip.text: text
        ToolTip.visible: recentProject && hovered
        onClicked: {
            if (!action && entry) entry.triggered()
            panel.dismissed()
        }
        Connections {
            target: command.action
            function onTriggered() { panel.dismissed() }
        }
        background: Rectangle {
            radius: 6
            color: command.down ? theme.pressed : command.hovered ? theme.hover : "transparent"
            border.width: command.visualFocus ? 2 : 0
            border.color: theme.accent
        }
        contentItem: RowLayout {
            spacing: 8
            Label {
                Layout.fillWidth: true
                text: command.recentProject ? command.text.replace(/\\/g,"/").split("/").pop() : (command.checked ? "✓  " : "") + command.text
                color: command.enabled ? theme.text : theme.disabledText
                wrapMode: command.recentProject ? Text.NoWrap : Text.Wrap
                elide: Text.ElideMiddle
            }
            Label {
                visible: text.length>0
                text: command.action ? String(command.action.shortcut || "") : ""
                color: theme.muted
                font.pixelSize: 11
            }
        }
    }

    component Section: Button {
        id: sectionButton
        property bool expanded: false
        Layout.fillWidth: true
        implicitHeight: 36
        padding: 8
        background: Rectangle {
            radius: 6
            color: sectionButton.hovered ? theme.hover : "transparent"
            border.width: sectionButton.visualFocus ? 2 : 0
            border.color: theme.accent
        }
        contentItem: RowLayout {
            Label {
                text: sectionButton.text
                Layout.fillWidth: true
                color: !sectionButton.enabled ? theme.disabledText : sectionButton.expanded ? theme.accent : theme.text
                font.weight: Font.DemiBold
            }
            Canvas {
                id: chevron
                Layout.preferredWidth: 12; Layout.preferredHeight: 12
                Connections { target: sectionButton; function onExpandedChanged() { chevron.requestPaint() } function onEnabledChanged() { chevron.requestPaint() } }
                Connections { target: theme; function onDarkChanged() { chevron.requestPaint() } }
                onPaint: {
                    const c=getContext("2d")
                    c.reset(); c.strokeStyle=sectionButton.enabled ? theme.muted : theme.disabledText
                    c.lineWidth=1.3; c.lineCap="round"; c.lineJoin="round"
                    c.beginPath()
                    if (sectionButton.expanded) { c.moveTo(3,4); c.lineTo(6,7); c.lineTo(9,4) }
                    else { c.moveTo(4,3); c.lineTo(7,6); c.lineTo(4,9) }
                    c.stroke()
                }
            }
        }
    }

    ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.margins: 8
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            width: scroll.availableWidth
            spacing: 2
            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 4
                Label { text: "Application menu"; color: theme.text; font.weight: Font.DemiBold; Layout.fillWidth: true }
                SpliceletButton {
                    text: "×"; implicitWidth: 28; implicitHeight: 28; padding: 4
                    Accessible.name: "Close application menu"
                    onClicked: panel.dismissed()
                }
            }
            Repeater {
                model: panel.menus
                delegate: ColumnLayout {
                    id: group
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    spacing: 0
                    Section {
                        objectName: "panelMenuSection" + group.index
                        Layout.fillWidth: true
                        text: group.modelData.title
                        expanded: panel.section===group.index
                        onClicked: panel.section=panel.section===group.index ? -1 : group.index
                        Accessible.name: group.modelData.title
                        Accessible.description: panel.section===group.index ? "Expanded" : "Collapsed"
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: panel.section===group.index
                        spacing: 0
                        Repeater {
                            model: group.modelData.count
                            delegate: ColumnLayout {
                                id: row
                                required property int index
                                readonly property var entry: group.modelData.itemAt(index)
                                readonly property var submenu: entry ? entry.subMenu : null
                                property bool expanded: false
                                Connections {
                                    target: panel
                                    function onCollapseSubmenus() { row.expanded = false }
                                }
                                Layout.fillWidth: true
                                spacing: 0
                                Command {
                                    visible: row.entry && !!row.entry.action
                                    entry: row.entry
                                }
                                Section {
                                    objectName: row.submenu ? "panelRecentProjects" : ""
                                    visible: !!row.submenu
                                    Layout.fillWidth: true
                                    text: row.entry ? row.entry.text : ""
                                    expanded: row.expanded
                                    enabled: row.entry ? row.entry.enabled : false
                                    onClicked: row.expanded=!row.expanded
                                }
                                Repeater {
                                    model: row.expanded && row.submenu ? row.submenu.count : 0
                                    delegate: Command {
                                        required property int index
                                        objectName: "panelRecentProject" + index
                                        recentProject: true
                                        entry: row.submenu.itemAt(index)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
