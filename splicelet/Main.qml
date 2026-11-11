import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: root
    required property var preview
    property url applicationIconSource: Qt.resolvedUrl("assets/splicelet.svg")
    readonly property alias uiTheme: themeColors
    readonly property var theme: themeColors
    Theme { id: themeColors; dark: preview.darkTheme }
    width: 1120; height: 790
    minimumWidth: 760; minimumHeight: 560
    visible: true
    flags: Qt.Window | Qt.CustomizeWindowHint | Qt.WindowSystemMenuHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint | Qt.ExpandedClientAreaHint | Qt.NoTitleBarBackgroundHint
    topPadding: 0
    title: "Splicelet — " + preview.projectName + (preview.projectDirty ? " *" : "")
    readonly property bool fullScreen: visibility === Window.FullScreen
    readonly property bool transportKeysEnabled: !preview.openingProject && !appMenu.opened && !timeInput.activeFocus && !properties.editing && !picker.visible && !exportOptions.visible && !exportPicker.visible && !projectPicker.visible && !savePicker.visible && !unsavedDialog.visible && !projectErrorDialog.visible && !aboutDialog.visible && !shortcutsDialog.visible && !spaceDialog.visible && !fileMenu.opened && !editMenu.opened && !recentMenu.opened && !viewMenu.opened && !helpMenu.opened && timeline.dragIndex<0 && timeline.resizeIndex<0
    readonly property bool fileDialogsClosed: !picker.visible && !exportOptions.visible && !exportPicker.visible && !projectPicker.visible && !savePicker.visible && !unsavedDialog.visible && !projectErrorDialog.visible && !aboutDialog.visible && !shortcutsDialog.visible && !spaceDialog.visible
    property bool restoreMaximized: false
    property var pendingAction: null
    property bool closingApproved: false
    component PanelTab: Button {
        id: panelTab
        required property int pageIndex
        readonly property bool selected: sourceTabs.currentIndex===pageIndex
        implicitWidth: 106
        implicitHeight: 36
        padding: 8
        Accessible.role: Accessible.PageTab
        Accessible.name: text
        onClicked: { properties.finishEditing(); appMenu.close(); sourceTabs.currentIndex=pageIndex }
        background: Rectangle {
            color: panelTab.selected ? theme.surface : panelTab.hovered ? theme.hover : "transparent"
            border.width: panelTab.visualFocus ? 2 : 0
            border.color: theme.accent
            radius: 8
        }
        contentItem: Item {
            Row {
                anchors.centerIn: parent
                spacing: 6
                Canvas {
                    id: panelIcon
                    width: 18; height: 18
                    Connections { target: panelTab; function onSelectedChanged() { panelIcon.requestPaint() } }
                    Connections { target: theme; function onDarkChanged() { panelIcon.requestPaint() } }
                    onPaint: {
                        const c = getContext("2d")
                        c.reset(); c.strokeStyle = panelTab.selected ? theme.accent : theme.muted
                        c.lineWidth = 1.4; c.lineCap = "round"; c.lineJoin = "round"
                        if (panelTab.pageIndex===0) {
                            for (let i=0; i<3; ++i) {
                                const x=3+i*6, y=i===1 ? 12 : 6
                                c.beginPath(); c.moveTo(x,1); c.lineTo(x,y-2.5); c.moveTo(x,y+2.5); c.lineTo(x,17); c.stroke()
                                c.beginPath(); c.arc(x,y,2,0,Math.PI*2); c.stroke()
                            }
                        } else {
                            c.strokeRect(1,2,16,14)
                            c.beginPath(); c.moveTo(1,12); c.lineTo(5,8); c.lineTo(10,13); c.lineTo(13,10); c.lineTo(17,14); c.stroke()
                            c.beginPath(); c.arc(12,6,1.5,0,Math.PI*2); c.stroke()
                        }
                    }
                }
                Text {
                    text: panelTab.text; font.pixelSize: 13
                    font.weight: panelTab.selected ? Font.DemiBold : Font.Normal
                    color: panelTab.selected ? theme.accent : theme.muted
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    function requestAction(action) {
        properties.finishEditing()
        if (preview.projectDirty) {
            pendingAction = action
            unsavedDialog.open()
        } else action()
    }
    function finishPending() {
        const action = pendingAction
        pendingAction = null
        if (action) action()
    }
    function saveCurrent(asNew) {
        properties.finishEditing()
        if (asNew || !preview.hasProjectPath) savePicker.open()
        else if (preview.saveProject()) finishPending()
        else pendingAction = null
    }
    onClosing: function(close) {
        properties.finishEditing()
        if (!closingApproved && preview.projectDirty) {
            close.accepted = false
            requestAction(function() { closingApproved = true; root.close() })
        }
    }
    component TransportButton: SpliceletButton {
        id: transport
        property string symbol: "play"
        implicitWidth: 42
        contentItem: Canvas {
            id: transportIcon
            implicitWidth: 18; implicitHeight: 18
            Connections { target: transport; function onSymbolChanged() { transportIcon.requestPaint() } function onEnabledChanged() { transportIcon.requestPaint() } function onHighlightedChanged() { transportIcon.requestPaint() } }
            Connections { target: theme; function onDarkChanged() { transportIcon.requestPaint() } }
            onPaint: {
                const c = getContext("2d")
                c.reset(); c.translate(width/2-9,height/2-9)
                c.fillStyle = !transport.enabled ? theme.disabledText : transport.highlighted ? "#ffffff" : theme.text
                c.strokeStyle = c.fillStyle; c.lineWidth = 1.5
                if (transport.symbol==="speaker" || transport.symbol==="muted") {
                    c.beginPath(); c.moveTo(1,7); c.lineTo(5,7); c.lineTo(9,3); c.lineTo(9,15); c.lineTo(5,11); c.lineTo(1,11); c.closePath(); c.fill()
                    c.beginPath()
                    if (transport.symbol==="muted") { c.moveTo(12,6); c.lineTo(17,12); c.moveTo(17,6); c.lineTo(12,12) }
                    else { c.arc(8,9,5,-.8,.8); c.moveTo(14.3,2.5); c.arc(8,9,9,-.8,.8) }
                    c.stroke()
                } else if (transport.symbol==="zoomIn" || transport.symbol==="zoomOut") {
                    c.beginPath(); c.arc(7,7,4.5,0,Math.PI*2); c.stroke()
                    c.beginPath(); c.moveTo(10.5,10.5); c.lineTo(16,16); c.moveTo(4.5,7); c.lineTo(9.5,7)
                    if (transport.symbol==="zoomIn") { c.moveTo(7,4.5); c.lineTo(7,9.5) }
                    c.stroke()
                } else if (transport.symbol==="cut") {
                    c.beginPath(); c.arc(4,13.5,2.5,0,Math.PI*2); c.moveTo(16.5,13.5); c.arc(14,13.5,2.5,0,Math.PI*2); c.stroke()
                    c.beginPath(); c.moveTo(5.5,11.5); c.lineTo(14,1.5); c.moveTo(12.5,11.5); c.lineTo(4,1.5); c.stroke()
                } else if (transport.symbol==="pause") { c.fillRect(4,3,3,12); c.fillRect(11,3,3,12) }
                else {
                    const previous = transport.symbol==="previous"
                    c.beginPath(); c.moveTo(previous ? 13 : 5,3); c.lineTo(previous ? 4 : 14,9); c.lineTo(previous ? 13 : 5,15); c.closePath(); c.fill()
                    if (transport.symbol==="previous") c.fillRect(1,3,2,12)
                    if (transport.symbol==="next") c.fillRect(16,3,2,12)
                }
            }
        }
    }
    component ShortcutMenuItem: MenuItem {
        id: menuItem
        objectName: action && action.objectName ? "menuCommand_" + action.objectName : ""
        leftPadding: padding
        indicator: null
        onTriggered: if (!subMenu) appMenu.close()
        contentItem: RowLayout {
            spacing: 0
            Label { text: menuItem.text; color: menuItem.enabled ? theme.text : theme.disabled; Layout.fillWidth: true; Layout.rightMargin: 28 }
            Label { text: menuItem.action ? (menuItem.action.objectName==="redoAction" ? "Ctrl+Shift+Z / Ctrl+Y" : (menuItem.action.shortcutLabel || menuItem.action.shortcut || "")) : ""; color: theme.muted; font.pixelSize: 12 }
            Item {
                Layout.preferredWidth: 16; Layout.preferredHeight: 16; Layout.leftMargin: 12
                Canvas {
                    id: menuCheck
                    anchors.fill: parent
                    visible: menuItem.checkable && menuItem.checked
                    onVisibleChanged: requestPaint()
                    Connections { target: menuItem; function onEnabledChanged() { menuCheck.requestPaint() } }
                    Connections { target: theme; function onDarkChanged() { menuCheck.requestPaint() } }
                    onPaint: {
                        const c = getContext("2d")
                        c.reset(); c.strokeStyle = menuItem.enabled ? theme.text : theme.disabled
                        c.lineWidth = 1.5; c.lineCap = "round"; c.lineJoin = "round"
                        c.beginPath(); c.moveTo(3,8); c.lineTo(6,11); c.lineTo(13,4); c.stroke()
                    }
                }
            }
        }
    }
    Rectangle {
        id: titleBar
        objectName: "windowTitleBar"
        width: parent.width
        z: 40
        visible: !root.fullScreen
        height: visible ? Math.max(36, root.SafeArea.margins.top) : 0
        color: theme.window
        // Leave Windows caption buttons in their native area on the right.
        MouseArea {
            objectName: "titleBarDragArea"
            property point pressPosition
            property bool moving: false
            anchors.fill: parent
            anchors.leftMargin: appMenu.opened ? appMenu.x + appMenu.width : 76
            anchors.rightMargin: Math.max(150, root.SafeArea.margins.right)
            onPressed: function(mouse) { pressPosition=Qt.point(mouse.x,mouse.y); moving=false }
            onPositionChanged: function(mouse) {
                if (pressed && !moving && Math.hypot(mouse.x-pressPosition.x,mouse.y-pressPosition.y)>=Qt.styleHints.startDragDistance) {
                    moving=true
                    root.startSystemMove()
                }
            }
            onDoubleClicked: root.visibility===Window.Maximized ? root.showNormal() : root.showMaximized()
        }
        Label {
            objectName: "windowTitleLabel"
            anchors.left: parent.left; anchors.leftMargin: 84
            anchors.right: parent.right; anchors.rightMargin: Math.max(158, root.SafeArea.margins.right+8)
            anchors.verticalCenter: parent.verticalCenter
            visible: !appMenu.opened
            text: root.title
            elide: Text.ElideRight
            color: theme.muted
            font.pixelSize: 12
        }
        Image {
            objectName: "systemMenuIcon"
            x: 12; anchors.verticalCenter: parent.verticalCenter
            width: 16; height: 16
            source: root.applicationIconSource
            fillMode: Image.PreserveAspectFit
            Accessible.role: Accessible.Button
            Accessible.name: "Window menu"
        }
        SpliceletButton {
            id: menuButton
            objectName: "menuButton"
            x: 36; anchors.verticalCenter: parent.verticalCenter
            width: 36; height: 30; implicitWidth: 36; implicitHeight: 30
            visible: !root.fullScreen
            padding: 0
            focusPolicy: Qt.StrongFocus
            onClicked: { properties.finishEditing(); appMenu.opened ? appMenu.close() : appMenu.open() }
            Accessible.name: "Application menu"
            background: Rectangle {
                radius: 8
                color: appMenu.opened ? theme.surface : menuButton.down ? theme.pressed : menuButton.hovered ? theme.hover : "transparent"
            }
            contentItem: Item {
                Column {
                    anchors.centerIn: parent
                    spacing: 4
                    Repeater { model: 3; Rectangle { width: 16; height: 1.5; radius: .75; color: theme.text } }
                }
            }
        }
    }
    Item {
        id: appMenu
        objectName: "applicationMenu"
        parent: titleBar
        x: 76; y: 0
        width: compactMenu.implicitWidth; height: titleBar.height
        z: 50
        property bool opened: false
        function reset() {
            recentMenu.close(); fileMenu.close(); editMenu.close(); viewMenu.close(); helpMenu.close()
            compactMenu.currentIndex = -1
            for (let i=0; i<compactMenu.count; ++i) {
                const item=compactMenu.itemAt(i)
                if (item) { item.highlighted=false; item.focus=false }
            }
        }
        function open() { properties.finishEditing(); reset(); opened = true; compactMenu.forceActiveFocus() }
        function close() { reset(); opened = false; timeInput.focus = false }
        MenuBar {
            id: compactMenu
            objectName: "compactMenuBar"
            // Keep the bar instantiated so shared shortcuts stay registered.
            visible: appMenu.opened
            height: titleBar.height
            delegate: MenuBarItem {
                id: categoryItem
                objectName: "menuCategory" + text
                height: titleBar.height
                hoverEnabled: true
                onHoveredChanged: {
                    if (!hovered || !appMenu.opened || !menu || menu.opened) return
                    for (let i=0; i<compactMenu.count; ++i) {
                        const item=compactMenu.itemAt(i)
                        if (item===categoryItem) compactMenu.currentIndex=i
                        else if (item && item.menu) item.menu.close()
                    }
                    if (!menu.opened) menu.popup(categoryItem,0,height)
                }
            }
            topPadding: 0; bottomPadding: 0; leftPadding: 0; rightPadding: 0
            background: Item {}
            Menu {
                id: fileMenu
                objectName: "fileMenu"
                width: 320
                title: "File"
                delegate: ShortcutMenuItem {}
                Action { text: "Open project..."; shortcut: "Ctrl+O"; enabled: !preview.exporting && !preview.busy && root.fileDialogsClosed; onTriggered: root.requestAction(function() { projectPicker.open() }) }
                Menu {
                    id: recentMenu
                    objectName: "recentMenu"
                    width: Math.min(420, root.width-fileMenu.width-56)
                    title: "Open recent project"
                    enabled: !preview.exporting && !preview.busy && root.fileDialogsClosed && preview.recentProjects.length>0
                    Instantiator {
                        model: preview.recentProjects
                        delegate: MenuItem {
                            required property string modelData
                            required property int index
                            objectName: "recentProject" + index
                            text: modelData.replace(/\\/g,"/").split("/").pop()
                            ToolTip.text: modelData
                            ToolTip.visible: hovered
                            onTriggered: { appMenu.close(); const path = modelData; root.requestAction(function() { preview.openRecentProject(path) }) }
                        }
                        onObjectAdded: function(index,object) { recentMenu.insertItem(index,object) }
                        onObjectRemoved: function(index,object) { recentMenu.removeItem(object) }
                    }
                }
                Action { text: "Save project"; shortcut: "Ctrl+S"; enabled: preview.canSaveProject && root.fileDialogsClosed; onTriggered: root.saveCurrent(false) }
                Action { text: "Save project as..."; shortcut: "Ctrl+Shift+S"; enabled: preview.canSaveProject && root.fileDialogsClosed; onTriggered: root.saveCurrent(true) }
                MenuSeparator {}
                Action { shortcut: "Ctrl+I"; text: "Import sources..."; enabled: !preview.exporting && !preview.busy && root.fileDialogsClosed; onTriggered: { properties.finishEditing(); picker.open() } }
                Action {
                    objectName: "exportAction"
                    text: "Export video..."; shortcut: "Ctrl+E"
                    enabled: preview.indexedReady && preview.duration>0 && !preview.busy && !preview.importing && !preview.exporting && root.fileDialogsClosed
                    onTriggered: { properties.finishEditing(); timeInput.focus = false; exportOptions.open() }
                }
            }
            Menu {
                id: editMenu
                objectName: "editMenu"
                width: 320
                title: "Edit"
                delegate: ShortcutMenuItem {}
                Action { objectName: "undoAction"; text: "Undo"; shortcut: "Ctrl+Z"; enabled: preview.canUndo && (root.transportKeysEnabled || editMenu.opened || appMenu.opened); onTriggered: { properties.finishEditing(); preview.undoCut() } }
                Action { objectName: "redoAction"; text: "Redo"; shortcut: "Ctrl+Shift+Z"; enabled: preview.canRedo && (root.transportKeysEnabled || editMenu.opened || appMenu.opened); onTriggered: { properties.finishEditing(); preview.redoCut() } }
                MenuSeparator {}
                // Shortcuts stay separate to preserve their non-repeating key behavior.
                Action { objectName: "joinAction"; property string shortcutLabel: "J"; text: "Join"; enabled: preview.canJoin && !preview.busy && root.fileDialogsClosed; onTriggered: { properties.finishEditing(); preview.joinSelected() } }
                Action { objectName: "deleteAction"; property string shortcutLabel: "Delete"; text: "Delete"; enabled: preview.selectionCount>0 && !preview.busy && root.fileDialogsClosed; onTriggered: { properties.finishEditing(); preview.deleteSelected() } }
                Action { objectName: "duplicateAction"; property string shortcutLabel: "D"; text: "Duplicate"; enabled: preview.indexedReady && !preview.busy && root.fileDialogsClosed; onTriggered: { properties.finishEditing(); preview.duplicateSelected() } }
                MenuSeparator {}
                Action { objectName: "unlinkAudioAction"; text: "Unlink audio"; enabled: preview.canUnlink && !preview.busy && root.fileDialogsClosed; onTriggered: { properties.finishEditing(); preview.unlinkAudio() } }
                Action { objectName: "addStartSpaceAction"; text: "Add space at start..."; enabled: preview.canSaveProject && !preview.busy && root.fileDialogsClosed && timeline.dragIndex<0 && timeline.resizeIndex<0; onTriggered: root.openSpaceDialog("start") }
                Action { objectName: "addEndSpaceAction"; text: "Add space at end..."; enabled: preview.canSaveProject && !preview.busy && root.fileDialogsClosed && timeline.dragIndex<0 && timeline.resizeIndex<0; onTriggered: root.openSpaceDialog("end") }
            }
            Menu {
                id: viewMenu
                objectName: "viewMenu"
                width: 320
                title: "View"
                delegate: ShortcutMenuItem {}
                Action { objectName: "darkThemeAction"; text: "Night theme"; checkable: true; checked: preview.darkTheme; onTriggered: preview.setDarkTheme(checked) }
                MenuSeparator {}
                Action { objectName: "fullScreenAction"; text: "Full screen"; shortcut: "F11"; enabled: root.fileDialogsClosed; onTriggered: root.toggleFullscreen() }
                Action { objectName: "followAction"; text: "Follow"; shortcut: "F"; checkable: true; checked: timeline.followEnabled; enabled: preview.loaded && (root.transportKeysEnabled || viewMenu.opened || appMenu.opened); onTriggered: timeline.followEnabled=checked }
                Action { text: "Zoom in"; shortcut: "Ctrl++"; enabled: preview.loaded && (root.transportKeysEnabled || viewMenu.opened || appMenu.opened); onTriggered: root.zoomTimeline(2) }
                Action { text: "Zoom out"; shortcut: "Ctrl+-"; enabled: preview.loaded && (root.transportKeysEnabled || viewMenu.opened || appMenu.opened); onTriggered: root.zoomTimeline(.5) }
                Action { text: "Zoom selection"; shortcut: "Z"; enabled: root.transportKeysEnabled || viewMenu.opened || appMenu.opened; onTriggered: timeline.zoomSelection() }
            }
            Menu {
                id: helpMenu
                objectName: "helpMenu"
                width: 320
                title: "Help"
                delegate: ShortcutMenuItem {}
                Action { objectName: "shortcutsAction"; text: "Shortcuts..."; enabled: root.fileDialogsClosed; onTriggered: { properties.finishEditing(); shortcutsDialog.open() } }
                Action { objectName: "aboutAction"; text: "About..."; enabled: root.fileDialogsClosed; onTriggered: { properties.finishEditing(); aboutDialog.open() } }
            }
        }
    }
    Dialog {
        id: aboutDialog
        objectName: "aboutDialog"
        title: "About Splicelet"
        anchors.centerIn: parent
        width: Math.min(root.width-48,460)
        modal: true
        standardButtons: Dialog.Ok
        ColumnLayout {
            width: parent.width
            spacing: 12
            Label { objectName: "applicationVersionLabel"; text: "Splicelet " + Qt.application.version; font.pixelSize: 26; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: "Small cuts. Precise stories."; color: theme.muted }
            Label { text: "A local video editor for Windows. Trim, arrange and export with frame-accurate control."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: "Built with Python, Qt Quick, PyAV, NumPy and FFmpeg.\nYour original sources stay untouched."; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.pixelSize: 12; color: theme.muted }
        }
    }
    Dialog {
        id: shortcutsDialog
        objectName: "shortcutsDialog"
        title: "Shortcuts"
        anchors.centerIn: parent
        width: Math.min(root.width-48,640)
        height: Math.min(root.height-80,650)
        modal: true
        standardButtons: Dialog.Ok
        ScrollView {
            id: shortcutsScroll
            objectName: "shortcutsScroll"
            anchors.fill: parent
            clip: true
            rightPadding: 14
            contentWidth: availableWidth
            contentHeight: shortcutContent.implicitHeight
            ScrollBar.vertical.policy: ScrollBar.AlwaysOn
            ColumnLayout {
                id: shortcutContent
                width: shortcutsScroll.availableWidth
                spacing: 14
                Repeater {
                    model: [
                        { title: "Files and projects", entries: [
                            ["Ctrl+O", "Open project"], ["Ctrl+S", "Save project"], ["Ctrl+Shift+S", "Save project as"],
                            ["Ctrl+I", "Import sources"], ["Ctrl+E", "Export video"]
                        ] },
                        { title: "Playback and navigation", entries: [
                            ["Space", "Play / pause"], ["Left / Right", "Jump backward / forward 5 seconds"],
                            ["Ctrl+Left / Right", "Previous / next clip boundary"], ["< / >", "Previous / next frame (pauses playback)"],
                            ["Home / End", "Go to project start / end"], ["Enter in time field", "Seek to the entered time"]
                        ] },
                        { title: "Timeline editing", entries: [
                            ["C", "Split before the displayed frame"], ["D", "Duplicate clip without ripple"],
                            ["Delete", "Delete selection, leaving gaps"], ["J", "Join two adjacent selected clips"],
                            ["Ctrl+Z", "Undo"], ["Ctrl+Shift+Z / Ctrl+Y", "Redo"],
                            ["Double-click clip", "Seek to the clicked point"], ["Ctrl+click", "Toggle clip selection"], ["Shift+click", "Select a consecutive range of clips"], ["Drag down from ruler", "Rectangle selection in the active lane; Ctrl toggles clips"], ["Drag selected clip", "Move a consecutive selection, keeping its gaps"], ["Alt while dragging", "Temporarily bypass snapping"]
                        ] },
                        { title: "View and zoom", entries: [
                            ["Ctrl++ / Ctrl+-", "Zoom in / out around the viewport center"], ["Ctrl+=", "Zoom in (alternative)"],
                            ["Ctrl+wheel", "Zoom around the pointer"], ["Wheel / two-finger scroll", "Pan the timeline (horizontal or vertical gesture)"], ["Shift+wheel", "Zoom waveform vertically over audio; pan elsewhere"],
                            ["Z", "Fit selection, or project with no selection"],
                            ["F", "Toggle centered playhead follow when zoomed"], ["Ctrl+M", "Open / close application menu"],
                            ["F11", "Toggle video full screen"], ["Double-click video", "Toggle video full screen"], ["Esc", "Exit full screen / close a dialog"]
                        ] }
                    ]
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 6
                        Label { text: modelData.title; font.weight: Font.DemiBold; color: theme.accent }
                        Repeater {
                            model: modelData.entries
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 16
                                Label { text: modelData[0]; Layout.preferredWidth: 175; wrapMode: Text.WordWrap; font.pixelSize: 12 }
                                Label { text: modelData[1]; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 12; color: theme.muted }
                            }
                        }
                    }
                }
            }
        }
    }
    FileDialog {
        id: projectPicker
        title: "Open project"
        nameFilters: ["Splicelet project (*.splicelet)"]
        onAccepted: preview.openProject(selectedFile)
    }
    FileDialog {
        id: savePicker
        objectName: "saveProjectDialog"
        title: "Save project as"
        fileMode: FileDialog.SaveFile
        nameFilters: ["Splicelet project (*.splicelet)"]
        defaultSuffix: "splicelet"
        onAccepted: { if (preview.saveProjectAs(selectedFile)) root.finishPending(); else root.pendingAction = null }
        onRejected: root.pendingAction = null
    }
    Dialog {
        id: unsavedDialog
        objectName: "unsavedProjectDialog"
        title: "Unsaved project"
        anchors.centerIn: parent
        modal: true
        standardButtons: Dialog.Save | Dialog.Discard | Dialog.Cancel
        Label { text: "Save changes to the current project?" }
        onAccepted: root.saveCurrent(false)
        onDiscarded: root.finishPending()
        onRejected: root.pendingAction = null
    }
    Dialog {
        id: spaceDialog
        objectName: "addSpaceDialog"
        property string side: "start"
        property string error: ""
        title: side==="start" ? "Add space at project start" : "Add space at project end"
        anchors.centerIn: parent
        width: Math.min(root.width-48,360)
        modal: true
        function commit() {
            const value = spaceSeconds.text.trim()
            if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(value) || !Number.isFinite(Number(value)) || Number(value)<=0) {
                error = "Enter a positive number of seconds using a decimal point."
                spaceSeconds.forceActiveFocus()
                return
            }
            if (preview.addSpace(side,value)) accept()
            else error = preview.status
        }
        onOpened: { spaceSeconds.forceActiveFocus(); spaceSeconds.selectAll() }
        ColumnLayout {
            width: parent.width
            spacing: 10
            Label { text: "How much space?" }
            RowLayout {
                TextField {
                    id: spaceSeconds
                    objectName: "spaceSeconds"
                    Layout.preferredWidth: 120
                    text: "10"
                    selectByMouse: true
                    focusPolicy: Qt.StrongFocus
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    Accessible.name: "Space duration in seconds"
                    onAccepted: spaceDialog.commit()
                    onTextEdited: spaceDialog.error=""
                }
                Label { text: "seconds"; color: theme.muted }
            }
            Label { text: "Black video and silence."; color: theme.muted; font.pixelSize: 12 }
            Label { text: spaceDialog.error; visible: text.length>0; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: "#b33c35"; font.pixelSize: 12 }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                SpliceletButton { text: "Cancel"; onClicked: spaceDialog.reject() }
                SpliceletButton { objectName: "confirmSpaceButton"; text: "Add space"; highlighted: true; onClicked: spaceDialog.commit() }
            }
        }
    }
    Dialog {
        id: projectErrorDialog
        objectName: "projectErrorDialog"
        property string message: ""
        title: "Project error"
        anchors.centerIn: parent
        width: Math.min(root.width-48,640)
        modal: true
        standardButtons: Dialog.Ok
        Label { width: parent.width; text: projectErrorDialog.message; wrapMode: Text.WrapAnywhere }
    }
    Connections {
        target: preview
        function onProjectError(message) { projectErrorDialog.message = message; projectErrorDialog.open() }
    }
    function openSpaceDialog(side) {
        properties.finishEditing(); timeInput.focus=false
        spaceDialog.side=side; spaceDialog.error=""; spaceSeconds.text="10"; spaceDialog.open()
    }
    function zoomTimeline(factor) { properties.finishEditing(); timeline.zoom(factor,timeline.width/2) }
    function toggleFullscreen() {
        properties.finishEditing(); appMenu.close()
        if (fullScreen) {
            if (restoreMaximized) showMaximized()
            else showNormal()
        } else {
            restoreMaximized = visibility === Window.Maximized
            timeInput.focus = false
            showFullScreen()
        }
    }
    color: theme.window
    palette.window: theme.window
    palette.windowText: theme.text
    palette.base: theme.surface
    palette.text: theme.text
    palette.button: theme.surface
    palette.buttonText: theme.text
    palette.mid: theme.line
    palette.dark: theme.disabled
    palette.light: theme.surface
    palette.highlight: theme.accent
    palette.highlightedText: theme.dark ? theme.window : "#ffffff"
    font.family: "Segoe UI"
    font.pixelSize: 14

    FileDialog {
        id: picker
        objectName: "importVideoDialog"
        title: "Import sources"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Video and audio (*.mkv *.mp4 *.mov *.avi *.webm *.m4v *.mts *.m2ts *.wav *.mp3 *.flac *.m4a *.aac *.ogg *.opus *.aif *.aiff)", "All files (*)"]
        onAccepted: { preview.importUrls(selectedFiles); sourceTabs.currentIndex=1 }
    }
    Dialog {
        id: exportOptions
        objectName: "exportOptionsDialog"
        title: "Export video"
        anchors.centerIn: parent
        width: Math.min(root.width-48,500)
        modal: true
        property bool selected: false
        property bool normalize: false
        property real level: -1
        property bool independent: false
        property string error: ""
        onOpened: {
            selectedRange.checked = false
            allRange.checked = true
            normalizeAudio.checked = false
            independentChannels.checked = false
            normalizeLevel.text = "-1"
            error = ""
        }
        function commit() {
            const value = normalizeLevel.text.trim()
            if (normalizeAudio.checked && (!/^-?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value) || !Number.isFinite(Number(value)) || Number(value)>0)) {
                error = "Enter a level at or below 0 dBFS using a decimal point."
                normalizeLevel.forceActiveFocus()
                return
            }
            selected = selectedRange.checked
            normalize = normalizeAudio.checked
            level = normalize ? Number(value) : -1
            independent = normalize && independentChannels.checked
            exportPicker.selectedFile = preview.exportFileUrl(selected)
            accept()
            exportPicker.open()
        }
        ColumnLayout {
            width: parent.width
            spacing: 10
            RowLayout {
                RadioButton { id: allRange; objectName: "exportAllRadio"; text: "All" }
                RadioButton { id: selectedRange; objectName: "exportSelectedRadio"; text: "Selected"; enabled: preview.selectionCount>0 }
            }
            Label {
                Layout.fillWidth: true
                text: selectedRange.checked ? "From the first selected clip to the last, including gaps." : "The entire timeline, including leading, internal and trailing gaps."
                color: theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap
            }
            CheckBox { id: normalizeAudio; objectName: "normalizeAudioCheck"; text: "Normalize audio"; enabled: preview.hasAudio }
            ColumnLayout {
                id: normalizationOptions
                objectName: "normalizationOptions"
                Layout.leftMargin: 24
                Layout.fillWidth: true
                enabled: normalizeAudio.checked && normalizeAudio.enabled
                opacity: enabled ? 1 : 0.4
                RowLayout {
                    Label { text: "Level" }
                    TextField {
                        id: normalizeLevel
                        objectName: "normalizationLevel"
                        Layout.preferredWidth: 90
                        selectByMouse: true
                        Accessible.name: "Normalization level in dBFS"
                        onAccepted: exportOptions.commit()
                        onTextEdited: exportOptions.error = ""
                    }
                    Label { text: "dBFS"; color: theme.muted }
                }
                CheckBox { id: independentChannels; objectName: "normalizeChannelsCheck"; text: "Normalize stereo channels independently" }
            }
            Label { Layout.fillWidth: true; visible: exportOptions.error.length>0; text: exportOptions.error; color: "#b33c35"; font.pixelSize: 12; wrapMode: Text.WordWrap }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                SpliceletButton { text: "Cancel"; onClicked: exportOptions.reject() }
                SpliceletButton { objectName: "continueExportButton"; text: "Continue"; highlighted: true; onClicked: exportOptions.commit() }
            }
        }
    }
    FileDialog {
        id: exportPicker
        objectName: "exportVideoDialog"
        title: "Export video"
        fileMode: FileDialog.SaveFile
        nameFilters: ["MP4 video (*.mp4)"]
        defaultSuffix: "mp4"
        options: FileDialog.DontConfirmOverwrite
        onAccepted: preview.exportClip(selectedFile,exportOptions.selected,exportOptions.normalize,exportOptions.level,exportOptions.independent)
    }
    Shortcut { sequence: "Escape"; enabled: appMenu.opened; onActivated: appMenu.close() }
    Shortcut { sequence: "Ctrl+M"; enabled: !root.fullScreen && root.fileDialogsClosed; onActivated: appMenu.opened ? appMenu.close() : appMenu.open() }
    Shortcut { sequence: "Ctrl+="; enabled: preview.loaded && root.transportKeysEnabled; onActivated: root.zoomTimeline(2) }
    Shortcut { sequence: "Space"; enabled: root.transportKeysEnabled; onActivated: preview.toggle() }
    Shortcut { sequence: "Left"; enabled: root.transportKeysEnabled; onActivated: preview.jump(-5) }
    Shortcut { sequence: "Right"; enabled: root.transportKeysEnabled; onActivated: preview.jump(5) }
    Shortcut { sequence: "Ctrl+Left"; enabled: root.transportKeysEnabled; onActivated: preview.jumpBoundary(-1) }
    Shortcut { sequence: "Ctrl+Right"; enabled: root.transportKeysEnabled; onActivated: preview.jumpBoundary(1) }
    Shortcut { sequence: "C"; autoRepeat: false; enabled: root.transportKeysEnabled && preview.indexedReady; onActivated: preview.cut() }
    Shortcut { sequence: "J"; autoRepeat: false; enabled: root.transportKeysEnabled; onActivated: preview.joinSelected() }
    Shortcut { sequence: "Delete"; autoRepeat: false; enabled: root.transportKeysEnabled; onActivated: preview.deleteSelected() }
    Shortcut { sequence: "D"; autoRepeat: false; enabled: root.transportKeysEnabled; onActivated: preview.duplicateSelected() }
    Shortcut { sequence: "Ctrl+Y"; enabled: root.transportKeysEnabled && preview.canRedo; onActivated: preview.redoCut() }
    Shortcut { sequence: "Escape"; autoRepeat: false; enabled: root.fullScreen && root.fileDialogsClosed; onActivated: root.toggleFullscreen() }
    Shortcut { sequence: "Home"; enabled: root.transportKeysEnabled; onActivated: { preview.seek(0); timeline.centerPlayhead() } }
    Shortcut { sequence: "End"; enabled: root.transportKeysEnabled; onActivated: { preview.seek(preview.duration); timeline.centerPlayhead() } }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.fullScreen ? 0 : 12
        anchors.topMargin: root.fullScreen ? 0 : titleBar.height + 12
        spacing: root.fullScreen ? 0 : 8
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 12
        Rectangle {
            visible: !root.fullScreen
            Layout.preferredWidth: 276
            Layout.minimumWidth: 276
            Layout.maximumWidth: 276
            Layout.fillHeight: true
            color: theme.well
            radius: 12
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 8
                spacing: 8
                RowLayout {
                    id: sourceTabs
                    objectName: "sidePanelTabs"
                    property int currentIndex: 0
                    Layout.fillWidth: true
                    spacing: 4
                    onCurrentIndexChanged: { properties.finishEditing(); appMenu.close() }
                    PanelTab { Layout.fillWidth: true; pageIndex: 0; text: "Properties"; objectName: "propertiesTab" }
                    PanelTab { Layout.fillWidth: true; pageIndex: 1; objectName: "sourceTab"; text: "Sources" }
                }
                StackLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    currentIndex: sourceTabs.currentIndex
                    Rectangle {
                        color: theme.surface; radius: 12
                        ClipProperties {
                            id: properties
                            anchors.fill: parent
                            preview: root.preview
                            enabled: !preview.openingProject
                            visible: preview.selectionCount===1
                        }
                        Label {
                            anchors.centerIn: parent; width: parent.width-24
                            visible: preview.selectionCount!==1
                            text: "Select one clip on the timeline to edit its properties."
                            wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; color: theme.muted
                        }
                    }
                    Rectangle {
                        color: theme.surface; radius: 12
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 10; spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "Imported sources"; Layout.fillWidth: true; font.weight: Font.DemiBold }
                                SpliceletButton { text: "Import"; enabled: !preview.exporting && !preview.busy; onClicked: picker.open() }
                            }
                            Label { text: preview.importing ? "Preparing sources…" : "Drag to the timeline, or add to the end."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            ListView {
                                id: sourceList
                                objectName: "sourceList"
                                Layout.fillWidth: true; Layout.fillHeight: true
                                clip: true; spacing: 6
                                model: preview.importedSources
                                ScrollBar.vertical: ScrollBar {}
                                delegate: Rectangle {
                                    id: sourceEntry
                                    required property var modelData
                                    readonly property int sourceIndex: modelData.index
                                    objectName: "sourceEntry"+sourceIndex
                                    width: sourceList.width; height: 77; radius: 8
                                    color: sourceMouse.containsMouse ? theme.hover : theme.clip
                                    Column {
                                        x: 8; y: 8; width: parent.width-16; spacing: 4
                                        Label { width: parent.width; text: sourceEntry.modelData.name; elide: Text.ElideMiddle; font.weight: Font.DemiBold; font.pixelSize: 12 }
                                        Label { text: sourceEntry.modelData.detail; color: theme.muted; font.pixelSize: 11 }
                                        Label { text: sourceEntry.modelData.kind + " · " + sourceEntry.modelData.durationText; color: theme.muted; font.pixelSize: 11 }
                                    }
                                    MouseArea {
                                        id: sourceMouse
                                        anchors.fill: parent; hoverEnabled: true
                                        enabled: !preview.exporting && !preview.importing
                                        preventStealing: true
                                        property bool dragging: false
                                        property point pressPoint
                                        onPressed: function(mouse) {
                                            properties.finishEditing()
                                            pressPoint=Qt.point(mouse.x,mouse.y)
                                        }
                                        onPositionChanged: function(mouse) {
                                            if (!pressed) return
                                            if (!dragging && Math.hypot(mouse.x-pressPoint.x,mouse.y-pressPoint.y)<10) return
                                            const point=mapToItem(root.contentItem,mouse.x,mouse.y)
                                            sourceGhost.x=point.x-16; sourceGhost.y=point.y-16
                                            dragging=true
                                        }
                                        onReleased: { if (dragging) sourceGhost.Drag.drop(); dragging=false }
                                        onCanceled: dragging=false
                                        onDoubleClicked: preview.appendSource(sourceEntry.sourceIndex)
                                        ToolTip.text: sourceEntry.modelData.path
                                        ToolTip.visible: containsMouse && !dragging
                                    }
                                    SpliceletButton {
                                        objectName: "appendSource"+sourceEntry.sourceIndex
                                        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 5
                                        text: "+"; implicitWidth: 28; implicitHeight: 24
                                        enabled: !preview.exporting && !preview.importing
                                        onClicked: preview.appendSource(sourceEntry.sourceIndex)
                                        ToolTip.text: "Add to end"; ToolTip.visible: hovered
                                        Accessible.name: "Add source to end"
                                    }
                                    Rectangle {
                                        id: sourceGhost
                                        parent: root.contentItem
                                        width: 220; height: 38; z: 100
                                        color: theme.selected; border.color: theme.accent; radius: 4
                                        visible: sourceMouse.dragging
                                        Drag.active: sourceMouse.dragging
                                        Drag.keys: ["splicelet-source"]
                                        Drag.source: sourceEntry
                                        Drag.hotSpot.x: 16; Drag.hotSpot.y: 16
                                        Label { anchors.fill: parent; anchors.margins: 8; text: sourceEntry.modelData.name; elide: Text.ElideMiddle }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            color: theme.well
            radius: 12
            Rectangle {
                anchors.centerIn: parent
                width: screen.paintedWidth; height: screen.paintedHeight
                color: "black"
                visible: preview.loaded
            }
            Image {
                id: screen
                objectName: "previewImage"
                anchors.fill: parent; anchors.margins: 1
                source: preview.frameSource
                cache: false
                asynchronous: false
                fillMode: Image.PreserveAspectFit
                smooth: true
                visible: preview.loaded
                opacity: preview.videoGain
            }
            Column {
                anchors.centerIn: parent; spacing: 12
                visible: !preview.loaded
                Label { anchors.horizontalCenter: parent.horizontalCenter; text: "A video, a precise position."; font.pixelSize: 24; color: theme.text }
                Label { anchors.horizontalCenter: parent.horizontalCenter; text: "Drop video or audio here, or choose Import sources"; color: theme.muted }
            }
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                onPressed: { properties.finishEditing(); appMenu.close(); timeInput.focus = false }
                onDoubleClicked: root.toggleFullscreen()
            }
        }
        }
        Rectangle {
            visible: !root.fullScreen
            Layout.fillWidth: true
            implicitHeight: bottomPanel.implicitHeight
            color: theme.well
            radius: 12
            ColumnLayout {
                id: bottomPanel
                anchors.fill: parent
                spacing: 5
                Timeline {
                    id: timeline
                    Layout.fillWidth: true
                    preview: root.preview
                    onInteracted: { properties.finishEditing(); appMenu.close(); timeInput.focus = false }
                }
                GridLayout {
                    columns: root.width<1000 ? 1 : 2
                    Layout.fillWidth: true
                    Layout.leftMargin: timeline.inset
                    Layout.rightMargin: timeline.inset
                    RowLayout {
                        Layout.fillWidth: true
                        TextField {
                            id: timeInput
                            objectName: "timeInput"
                            Layout.preferredWidth: root.width<820 ? 124 : 148
                            enabled: preview.loaded
                            font.family: "Consolas"
                            horizontalAlignment: Text.AlignHCenter
                            selectByMouse: true
                            Accessible.name: "Go to time"
                            background: Rectangle {
                                implicitWidth: 200; implicitHeight: 40
                                radius: 6; color: theme.window
                                border.width: timeInput.activeFocus ? 1 : 0
                                border.color: theme.accent
                            }
                            onAccepted: { preview.seekText(text); focus = false }
                            Binding { target: timeInput; property: "text"; value: preview.positionText; when: !timeInput.activeFocus; restoreMode: Binding.RestoreNone }
                        }
                        Label { text: "/ " + preview.durationText; color: theme.muted; font.family: "Consolas" }
                        TransportButton { objectName: "previousFrameButton"; symbol: "previous"; enabled: preview.indexedReady; focusPolicy: Qt.NoFocus; onClicked: preview.step(-1); Accessible.name: "Previous frame"; ToolTip.text: "Previous frame · <"; ToolTip.visible: hovered }
                        TransportButton {
                            objectName: "playButton"
                            symbol: preview.playing ? "pause" : "play"
                            highlighted: true
                            Layout.preferredWidth: 48
                            enabled: preview.loaded
                            focusPolicy: Qt.NoFocus
                            onClicked: preview.toggle()
                            Accessible.name: preview.playing ? "Pause" : "Play"
                            ToolTip.text: (preview.playing ? "Pause" : "Play")+" · Space"
                            ToolTip.visible: hovered
                        }
                        TransportButton { objectName: "nextFrameButton"; symbol: "next"; enabled: preview.indexedReady; focusPolicy: Qt.NoFocus; onClicked: preview.step(1); Accessible.name: "Next frame"; ToolTip.text: "Next frame · >"; ToolTip.visible: hovered }
                        Label { objectName: "frameLabel"; text: preview.frameLabel; color: theme.muted; font.pixelSize: 12 }
                        Label {
                            objectName: "selectedLengthLabel"
                            visible: preview.selectionCount>0
                            Layout.leftMargin: 16
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: "Selected length: "+preview.selectedLengthText
                            elide: Text.ElideRight
                            color: theme.muted; font.pixelSize: 12
                            ToolTip.text: text; ToolTip.visible: selectedLengthHover.hovered
                            HoverHandler { id: selectedLengthHover }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    RowLayout {
                        Layout.alignment: Qt.AlignRight
                        TransportButton { objectName: "cutButton"; symbol: "cut"; implicitWidth: 32; padding: 6; enabled: preview.indexedReady && !preview.busy; focusPolicy: Qt.NoFocus; onClicked: { properties.finishEditing(); preview.cut() } Accessible.name: "Split clip"; ToolTip.text: "Split at playhead · C"; ToolTip.visible: hovered }
                        TransportButton { objectName: "zoomOutButton"; symbol: "zoomOut"; implicitWidth: 32; padding: 6; enabled: preview.loaded; focusPolicy: Qt.NoFocus; onClicked: root.zoomTimeline(.5); Accessible.name: "Zoom out"; ToolTip.text: "Zoom out · Ctrl+-"; ToolTip.visible: hovered }
                        TransportButton { objectName: "zoomInButton"; symbol: "zoomIn"; implicitWidth: 32; padding: 6; enabled: preview.loaded; focusPolicy: Qt.NoFocus; onClicked: root.zoomTimeline(2); Accessible.name: "Zoom in"; ToolTip.text: "Zoom in · Ctrl++"; ToolTip.visible: hovered }
                        TransportButton {
                            objectName: "volumeButton"
                            symbol: preview.muted || preview.volume===0 ? "muted" : "speaker"
                            enabled: preview.audioEnabled
                            focusPolicy: Qt.NoFocus
                            onClicked: preview.toggleMute()
                            Accessible.name: !preview.audioEnabled ? "Audio unavailable" : preview.muted ? "Unmute" : "Mute"
                            ToolTip.text: !preview.audioEnabled ? "Audio unavailable" : (preview.muted ? "Muted · " : "Listening volume · ")+Math.round(preview.volume*100)+"%"
                            ToolTip.visible: hovered
                        }
                        Slider {
                            id: volumeSlider
                            objectName: "volumeSlider"
                            Layout.preferredWidth: 100
                            from: 0; to: 2.; stepSize: .01
                            value: preview.volume
                            enabled: preview.audioEnabled
                            Accessible.name: "Listening volume"
                            onMoved: preview.setVolume(value)
                            ToolTip.text: Math.round(value*100)+"%"+(value>1 ? " · May distort" : "")
                            ToolTip.visible: hovered || pressed
                            handle: Rectangle {
                                x: volumeSlider.leftPadding+volumeSlider.visualPosition*(volumeSlider.availableWidth-width)
                                y: volumeSlider.topPadding+(volumeSlider.availableHeight-height)/2
                                implicitWidth: 14; implicitHeight: 14; radius: 7
                                color: volumeSlider.pressed ? theme.pressed : theme.surface
                                border.color: volumeSlider.activeFocus ? theme.accent : theme.disabled
                            }
                            background: Rectangle {
                                x: volumeSlider.leftPadding+volumeSlider.handle.width/2
                                y: volumeSlider.topPadding+volumeSlider.availableHeight/2-height/2
                                width: volumeSlider.availableWidth-volumeSlider.handle.width; height: 4; radius: 2; color: theme.line
                                Rectangle { width: volumeSlider.visualPosition*parent.width; height: parent.height; radius: 2; color: theme.accent }
                                Rectangle { x: parent.width/2-width/2; anchors.verticalCenter: parent.verticalCenter; width: 2; height: 16; color: "#c34545" }
                            }
                        }
                    }
                }
                RowLayout {
                    objectName: "statusRow"
                    Layout.fillWidth: true
                    Layout.leftMargin: timeline.inset
                    Layout.rightMargin: timeline.inset
                    Layout.preferredHeight: 24
                    spacing: 8
                    BusyIndicator { visible: preview.busy; running: visible; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
                    Label {
                        objectName: "statusText"
                        text: [preview.exportStatus, preview.status, preview.loaded && !preview.indexedReady ? "Indexing…" : ""].filter(function(s) { return s.length>0 }).join(" · ")
                        color: theme.muted; elide: Text.ElideMiddle; Layout.fillWidth: true; font.pixelSize: 11
                        ToolTip.text: text; ToolTip.visible: statusMouse.containsMouse && truncated
                        MouseArea { id: statusMouse; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                    }
                    ProgressBar { visible: preview.exporting; value: preview.exportProgress; Layout.preferredWidth: 140 }
                    Label { visible: preview.exporting; text: Math.round(preview.exportProgress*100)+" %"; color: theme.muted; font.pixelSize: 11 }
                    SpliceletButton { visible: preview.exporting; text: "Cancel"; implicitHeight: 24; padding: 3; onClicked: preview.cancelExport() }
                }
            }
        }
    }
    DropArea {
        objectName: "fileImportDropArea"
        anchors.fill: parent
        anchors.topMargin: root.fullScreen ? 0 : titleBar.height
        z: 90
        keys: ["text/uri-list"]
        enabled: !preview.exporting && !preview.busy
        onEntered: function(drag) { drag.accepted = drag.hasUrls && drag.urls.length>0 && (drag.supportedActions & Qt.CopyAction)!==0 }
        onDropped: function(drop) {
            if (drop.hasUrls && drop.urls.length && !preview.exporting && !preview.busy) {
                properties.finishEditing()
                appMenu.close()
                preview.importUrls(drop.urls)
                sourceTabs.currentIndex=1
                drop.accept(Qt.CopyAction)
            }
        }
    }
}
