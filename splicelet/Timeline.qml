import QtQuick
import QtQuick.Window
import QtQuick.Controls

Item {
    readonly property var theme: ApplicationWindow.window.uiTheme
    id: timeline
    required property var preview
    enabled: !preview.openingProject
    signal interacted()
    objectName: "editTimeline"
    implicitHeight: (scroll.visible ? scroll.y+scroll.height : preview.hasAudio ? audioLaneY+audioLaneHeight : 91)+6
    readonly property real audioLaneY: 96
    readonly property real audioLaneHeight: 44
    property real waveformGain: 1
    clip: true
    readonly property real inset: 12
    readonly property real span: Math.max(1,width-2*inset)
    property real viewStart: 0
    property real viewDuration: 0
    property bool followEnabled: false
    readonly property real followPosition: preview.position
    function followPlayhead() {
        if (followEnabled) viewStart = visibleDuration<totalDuration-.000001 ? preview.position-visibleDuration/2 : 0
    }
    onFollowPositionChanged: followPlayhead()
    onVisibleDurationChanged: followPlayhead()
    onFollowEnabledChanged: if (followEnabled) followPlayhead()
    readonly property real totalDuration: Math.max(.001,preview.workspaceDuration,resizeIndex>=0 && resizeMoved && resizeSide==="right" ? resizeEnd+secondsPerPixel*40 : 0)
    readonly property real visibleDuration: viewDuration>0 ? Math.min(Math.max(.001,preview.workspaceDuration),viewDuration) : Math.max(.001,preview.duration)
    readonly property real secondsPerPixel: visibleDuration/span
    readonly property real tickStep: chooseTick()
    readonly property var ticks: makeTicks()
    readonly property var minorTicks: makeMinorTicks()
    property int dragIndex: -1
    property real dragStart: 0
    property var dragClips: []
    property real pressX: 0
    property real pressView: 0
    property real originalStart: 0
    property int resizeIndex: -1
    property bool resizeMoved: false
    property string resizeSide: "right"
    property real resizeStart: 0
    property real resizeEnd: 0
    property real resizeOriginalEdge: 0
    property real resizeMouseX: 0
    property int resizeModifiers: 0
    function isDragging(index) { return dragIndex>=0 && dragClips.some(function(clip) { return clip.index===index }) }
    readonly property var overlaps: {
        const clips = preview.clips
        const result = []
        for (let i=1;i<clips.length;i++) {
            const left=clips[i-1], right=clips[i]
            if (left.lane===right.lane && right.start<left.end)
                result.push({lane:right.lane,start:right.start,end:Math.min(left.end,right.end),left:left.index,right:right.index})
        }
        return result
    }
    function xAt(t) { return inset+(t-viewStart)/secondsPerPixel }
    DropArea {
        id: sourceDrop
        anchors.fill: parent
        keys: ["splicelet-source"]
        property real dropPosition: 0
        onPositionChanged: function(drag) {
            let raw = preview.duration>0 ? Math.max(0,timeline.viewStart+(drag.x-timeline.inset)*timeline.secondsPerPixel) : 0
            dropPosition = (drag.modifiers & Qt.AltModifier) ? raw : preview.snapPosition(raw,timeline.span*Math.max(.001,preview.duration)/timeline.visibleDuration)
        }
        onEntered: function(drag) { dropPosition=preview.duration>0 ? Math.max(0,timeline.viewStart+(drag.x-timeline.inset)*timeline.secondsPerPixel) : 0 }
        onDropped: function(drop) {
            if (drop.source && !preview.exporting && !preview.importing) {
                timeline.interacted()
                preview.insertSource(drop.source.sourceIndex,dropPosition,drop.y>=timeline.audioLaneY ? "audio" : "video")
                drop.acceptProposedAction()
            }
        }
        Rectangle {
            visible: sourceDrop.containsDrag
            x: timeline.xAt(sourceDrop.dropPosition); y: 20
            width: 2; height: parent.height-35; color: theme.accent; z: 40
        }
    }
    function positionAt(x,modifiers) {
        let raw = Math.max(0,Math.min(preview.duration,viewStart+(x-inset)*secondsPerPixel))
        return (modifiers & Qt.AltModifier) ? raw : preview.snapPosition(raw,span*Math.max(.001,preview.duration)/visibleDuration)
    }
    function updateResize(x,modifiers) {
        resizeMouseX=x; resizeModifiers=modifiers
        if (!resizeMoved && Math.abs(x-pressX)<4) return
        resizeMoved=true
        let target=resizeOriginalEdge+(x-pressX)*secondsPerPixel+viewStart-pressView
        let result=preview.resizeTarget(resizeIndex,resizeSide,target,secondsPerPixel,Boolean(modifiers & Qt.AltModifier))
        resizeStart=result.start; resizeEnd=result.end
    }
    function clampView(value) { return Math.max(0,Math.min(totalDuration-visibleDuration,value)) }
    function zoom(factor,x) {
        let ratio = Math.max(0,Math.min(1,(x-inset)/span))
        let anchor = viewStart+ratio*visibleDuration
        let duration = Math.max(.1,Math.min(totalDuration,visibleDuration/factor))
        viewDuration = Math.abs(duration-preview.duration)<.000001 ? 0 : duration
        if (followEnabled) followPlayhead()
        else viewStart = clampView(anchor-ratio*visibleDuration)
    }
    function pan(steps) { followEnabled=false; viewStart = clampView(viewStart-steps*visibleDuration*.15) }
    function zoomSelection() {
        let range = preview.selectionRange
        if (!preview.selectionCount) { viewDuration=0; viewStart=0; return }
        let duration = Math.max(.1,(range.end-range.start)*1.12)
        viewDuration = duration>=totalDuration ? 0 : duration
        if (followEnabled) followPlayhead()
        else viewStart = clampView((range.start+range.end-visibleDuration)/2)
    }
    function chooseTick() {
        let minimum = visibleDuration*95/span
        let steps = [.001,.002,.005,.01,.02,.05,.1,.2,.5,1,2,5,10,15,30,60,120,300,600,1800,3600]
        for (let s of steps) if (s>=minimum) return s
        return 3600*Math.ceil(minimum/3600)
    }
    function rulerTime(seconds) {
        let decimals = Math.max(0,Math.min(3,Math.ceil(-Math.log10(tickStep))))
        let scale = Math.pow(10,decimals)
        let units = Math.round(seconds*scale)
        let s = Math.floor(units/scale)
        return (s>=3600 ? Math.floor(s/3600)+":" : "")+String(Math.floor(s/60)%60).padStart(2,"0")+":"+String(s%60).padStart(2,"0")
            +(decimals ? "."+String(units%scale).padStart(decimals,"0") : "")
    }
    function makeTicks() {
        let result = []
        let first = Math.max(0,Math.ceil(viewStart/tickStep-.000001)*tickStep)
        for (let t=first;t<=Math.min(totalDuration,viewStart+visibleDuration)+.000001;t+=tickStep) result.push({time:t,label:rulerTime(t)})
        return result
    }
    function makeMinorTicks() {
        let result = []
        let step = tickStep/5
        let first = Math.max(0,Math.ceil(viewStart/step-.000001))
        let last = Math.floor(Math.min(totalDuration,viewStart+visibleDuration)/step+.000001)
        for (let i=first;i<=last;i++) {
            if (i%5===0) continue
            let x = xAt(i*step)
            let clear = true
            for (let tick of ticks) {
                let halfWidth = tick.label.length*3.2
                let center = Math.max(inset+halfWidth,Math.min(width-inset-halfWidth,xAt(tick.time)))
                if (Math.abs(x-center)<halfWidth+3) { clear=false; break }
            }
            if (clear && x>=inset && x<=width-inset) result.push(i*step)
        }
        return result
    }
    Connections {
        target: preview
        function onEditChanged() {
            if (!preview.indexedReady) { timeline.followEnabled=false; timeline.viewDuration=0; timeline.viewStart=0; timeline.waveformGain=1 }
            else if (timeline.followEnabled) timeline.followPlayhead()
            else timeline.viewStart=timeline.clampView(timeline.viewStart)
        }
    }
    Timer {
        interval: 40; repeat: true; running: timeline.resizeIndex>=0 && timeline.resizeMoved
        onTriggered: {
            let delta=timeline.resizeMouseX>timeline.width-timeline.inset-20 ? 1 : timeline.resizeMouseX<timeline.inset+20 ? -1 : 0
            if (delta) {
                timeline.viewStart=timeline.clampView(timeline.viewStart+delta*timeline.visibleDuration*.02)
                timeline.updateResize(timeline.resizeMouseX,timeline.resizeModifiers)
            }
        }
    }
    Rectangle { anchors.fill: parent; color: theme.timeline; radius: 12 }
    MouseArea {
        id: selectionMouse
        objectName: "timelineRuler"
        x: 0; y: 0; width: timeline.width; height: 36
        enabled: preview.loaded
        preventStealing: true
        property point start: Qt.point(0,0)
        property point current: Qt.point(0,0)
        property bool selecting: false
        property bool toggle: false
        property string gesture: ""
        property string lane: "video"
        property var selectionBaseline: []
        function refreshBoxSelection() {
            const left=Math.min(start.x,current.x), right=Math.max(start.x,current.x)
            const top=Math.min(start.y,current.y)+y, bottom=Math.max(start.y,current.y)+y
            const hits=preview.clips.filter(function(clip) {
                const clipY=clip.lane==="audio" ? timeline.audioLaneY : 38
                return clip.lane===lane && timeline.xAt(clip.start)<right && timeline.xAt(clip.end)-2>left
                    && clipY<bottom && clipY+(clip.lane==="audio" ? timeline.audioLaneHeight : 53)>top
            }).map(function(clip) { return clip.index })
            preview.selectClips(hits,lane,selectionBaseline,toggle)
        }
        onPressed: function(mouse) {
            timeline.followEnabled=false
            timeline.interacted()
            start=Qt.point(mouse.x,mouse.y); current=start; selecting=false; gesture=""
            lane=preview.selectionLane
            toggle=Boolean(mouse.modifiers & Qt.ControlModifier)
            selectionBaseline=preview.clips.filter(function(clip) { return clip.lane===selectionMouse.lane && clip.selected }).map(function(clip) { return clip.index })
        }
        onPositionChanged: function(mouse) {
            if (!pressed) return
            current=Qt.point(Math.max(0,Math.min(width,mouse.x)),Math.max(0,Math.min(timeline.height,mouse.y)))
            if (!gesture && Math.hypot(current.x-start.x,current.y-start.y)<4) return
            if (!gesture) {
                gesture=mouse.y>=height || Math.abs(mouse.y-start.y)>=Math.abs(mouse.x-start.x) ? "box" : "scrub"
                if (gesture==="scrub") preview.beginScrub()
            }
            if (gesture==="scrub") preview.seek(timeline.positionAt(mouse.x,mouse.modifiers))
            else if (current.y>=height || selecting) {
                selecting=true
                refreshBoxSelection()
            }
        }
        onReleased: function(mouse) {
            if (gesture==="scrub") preview.endScrub(timeline.positionAt(mouse.x,mouse.modifiers))
            else if (!selecting) {
                preview.beginScrub(); preview.endScrub(timeline.positionAt(mouse.x,mouse.modifiers))
            }
            selecting=false
        }
        onCanceled: {
            if (selecting) preview.selectClips(selectionBaseline,lane,[],false)
            if (gesture==="scrub") preview.endScrub(preview.position)
            selecting=false
        }
    }
    Rectangle {
        objectName: "selectionRectangle"
        z: 5; visible: selectionMouse.selecting
        x: Math.min(selectionMouse.start.x,selectionMouse.current.x)
        y: selectionMouse.y+Math.min(selectionMouse.start.y,selectionMouse.current.y)
        width: Math.abs(selectionMouse.current.x-selectionMouse.start.x)
        height: Math.abs(selectionMouse.current.y-selectionMouse.start.y)
        color: theme.selected; opacity: .55
        border.color: theme.accent; border.width: 1
    }
    Repeater {
        model: timeline.minorTicks
        Rectangle {
            required property real modelData
            x: Math.round(timeline.xAt(modelData)); y: 10
            width: 1; height: 4; color: theme.tick; opacity: .55
        }
    }
    Repeater {
        model: timeline.ticks
        Label {
            required property var modelData
            x: Math.max(timeline.inset,Math.min(timeline.width-timeline.inset-implicitWidth,timeline.xAt(modelData.time)-implicitWidth/2))
            y: 5; text: modelData.label; font.pixelSize: 11; color: theme.muted
        }
    }
    Repeater {
        model: preview.gaps
        Item {
            id: gapItem
            required property var modelData
            objectName: "gap-"+modelData.index
            x: timeline.xAt(modelData.start); y: modelData.lane==="audio" ? timeline.audioLaneY : 38
            width: (modelData.end-modelData.start)/timeline.secondsPerPixel; height: modelData.lane==="audio" ? timeline.audioLaneHeight : 53
            Rectangle {
                id: gapSurface
                objectName: "gap-surface-"+gapItem.modelData.index
                // Bound texture allocation to the viewport even for very long gaps.
                x: Math.max(0,-gapItem.x)
                width: Math.max(0,Math.min(gapItem.width-2,timeline.width-gapItem.x)-x)
                height: parent.height
                radius: 4
                color: theme.gap
                clip: true
                Canvas {
                    id: gapHatch
                    Connections { target: theme; function onDarkChanged() { gapHatch.requestPaint() } }
                    anchors.fill: parent; anchors.margins: 1
                    onWidthChanged: requestPaint()
                    onHeightChanged: requestPaint()
                    onPaint: {
                        const c = getContext("2d")
                        c.reset()
                        c.strokeStyle = theme.hatch; c.globalAlpha = .5; c.lineWidth = 1
                        c.beginPath()
                        for (let x=-height; x<width; x+=10) { c.moveTo(x,0); c.lineTo(x+height,height) }
                        c.stroke()
                    }
                }
                Rectangle { anchors.fill: parent; radius: 4; color: "transparent"; border.color: theme.gapBorder }
            }
            MouseArea {
                id: gapMouse
                anchors.fill: parent; hoverEnabled: true
                acceptedButtons: Qt.NoButton; cursorShape: Qt.ArrowCursor
            }
            Rectangle {
                id: trash
                objectName: "remove-gap-"+gapItem.modelData.index
                readonly property real visibleLeft: Math.max(timeline.inset,gapItem.x)
                readonly property real visibleRight: Math.min(timeline.width-timeline.inset,gapItem.x+gapItem.width)
                x: (visibleLeft+visibleRight)/2-gapItem.x-width/2
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(30,Math.max(0,visibleRight-visibleLeft)); height: Math.min(30,gapItem.height-2); radius: 4
                visible: width>=12 && (gapMouse.containsMouse || trashMouse.containsMouse) && timeline.dragIndex<0 && timeline.resizeIndex<0
                color: trashMouse.containsMouse ? "#fbdcda" : theme.surface
                border.color: "#b56660"
                Accessible.role: Accessible.Button
                Accessible.name: "Remove gap"
                Item {
                    anchors.centerIn: parent; width: 14; height: 17
                    Rectangle { x: 2; y: 5; width: 10; height: 12; radius: 1; color: "transparent"; border.color: "#9d3932" }
                    Rectangle { x: 0; y: 3; width: 14; height: 2; color: "#9d3932" }
                    Rectangle { x: 5; y: 0; width: 4; height: 3; color: "transparent"; border.color: "#9d3932" }
                    Rectangle { x: 5; y: 8; width: 1; height: 6; color: "#9d3932" }
                    Rectangle { x: 8; y: 8; width: 1; height: 6; color: "#9d3932" }
                }
                MouseArea {
                    id: trashMouse
                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: { timeline.interacted(); preview.removeGap(gapItem.modelData.index) }
                }
                ToolTip.visible: trashMouse.containsMouse
                ToolTip.delay: 500
                ToolTip.text: "Remove the gap and shift later clips to the left"
            }
        }
    }
    Repeater {
        model: preview.clips
        Rectangle {
            id: clipItem
            required property var modelData
            objectName: "clip-"+modelData.index
            x: timeline.xAt(modelData.start)
            y: modelData.lane==="audio" ? timeline.audioLaneY : 38
            width: Math.max(1,(modelData.end-modelData.start)/timeline.secondsPerPixel-2)
            height: modelData.lane==="audio" ? timeline.audioLaneHeight : 53; radius: 4
            opacity: timeline.isDragging(modelData.index) || (timeline.resizeIndex>=0 && (preview.lanesLinked ? timeline.resizeIndex%1000000===modelData.index%1000000 : timeline.resizeIndex===modelData.index)) ? .4 : 1
            color: modelData.selected ? theme.selected : theme.clip
            border.color: modelData.selected ? theme.accent : theme.tick
            border.width: modelData.selected ? 3 : 1
            clip: true
            Accessible.role: Accessible.Button
            Accessible.name: "Clip "+(modelData.index+1)+", "+modelData.rangeText
            readonly property real visibleStart: Math.max(modelData.start,timeline.viewStart)
            readonly property real visibleEnd: Math.min(modelData.end,timeline.viewStart+timeline.visibleDuration)
            readonly property var thumbnails: {
                const revision=preview.visualRevision
                return modelData.lane==="video" ? preview.timelineThumbnails(modelData.index,visibleStart,visibleEnd,timeline.secondsPerPixel*90) : []
            }
            Repeater {
                model: clipItem.thumbnails
                Image {
                    required property var modelData
                    x: (modelData.start-clipItem.modelData.start)/timeline.secondsPerPixel+2
                    y: 2; height: clipItem.height-4
                    width: Math.max(0,(modelData.end-modelData.start)/timeline.secondsPerPixel-1)
                    source: modelData.url
                    asynchronous: true
                    sourceSize.width: 160; sourceSize.height: 90
                    fillMode: Image.PreserveAspectCrop
                    opacity: .85
                }
            }
            Repeater {
                model: timeline.overlaps.filter(function(overlap) { return overlap.right===clipItem.modelData.index })
                Rectangle {
                    required property var modelData
                    objectName: "overlap-"+modelData.left+"-"+modelData.right
                    x: (modelData.start-clipItem.modelData.start)/timeline.secondsPerPixel
                    y: 2
                    width: Math.max(1,(modelData.end-modelData.start)/timeline.secondsPerPixel)
                    height: clipItem.height-4
                    color: "#b3cbb9eb"
                }
            }
            Rectangle {
                visible: clipItem.modelData.lane!=="audio"
                x: clipLabel.x-3; y: clipLabel.y-1
                width: Math.min(clipLabel.width+6,clipLabel.implicitWidth+6); height: clipLabel.height+2
                color: theme.caption; radius: 2
            }
            Column {
                id: clipLabel
                visible: clipItem.modelData.lane!=="audio"
                x: Math.max(10,timeline.inset-parent.x+8)
                width: Math.max(0,Math.min(230,parent.width-x-8,timeline.width-timeline.inset-parent.x-x-8))
                anchors.verticalCenter: parent.verticalCenter
                spacing: 3
                Label { width: parent.width; text: modelData.label; elide: Text.ElideRight; color: theme.text; font.pixelSize: 12; font.weight: Font.DemiBold }
                Label { width: parent.width; text: modelData.rangeText; elide: Text.ElideRight; color: theme.muted; font.pixelSize: 10 }
            }
            Canvas {
                id: waveform
                Connections { target: theme; function onDarkChanged() { waveform.requestPaint() } }
                visible: clipItem.modelData.lane==="audio"
                x: (clipItem.visibleStart-clipItem.modelData.start)/timeline.secondsPerPixel+2
                width: Math.max(0,(clipItem.visibleEnd-clipItem.visibleStart)/timeline.secondsPerPixel-4)
                height: clipItem.height-6; anchors.verticalCenter: parent.verticalCenter
                onHeightChanged: requestPaint()
                Connections {
                    target: timeline
                    function onWaveformGainChanged() { waveform.requestPaint() }
                }
                property var peaks: {
                    const revision=preview.visualRevision
                    return visible ? preview.waveformColumns(clipItem.modelData.index,clipItem.visibleStart,clipItem.visibleEnd,Math.ceil(width)) : []
                }
                onPeaksChanged: requestPaint()
                onPaint: {
                    const c=getContext("2d"); c.reset(); c.strokeStyle=theme.wave; c.lineWidth=1
                    c.beginPath(); c.moveTo(0,height/2); c.lineTo(width,height/2); c.stroke()
                    c.beginPath()
                    for (let i=0;i<peaks.length;i++) {
                        const x=(i+.5)*width/peaks.length
                        c.moveTo(x,height/2-Math.min(1,peaks[i][1]*timeline.waveformGain)*(height/2-1))
                        c.lineTo(x,height/2-Math.max(-1,peaks[i][0]*timeline.waveformGain)*(height/2-1))
                    }
                    c.stroke()
                }
            }
        }
    }
    // Keep hit testing independent of the opaque thumbnail stacking order.
    Repeater {
        model: preview.clips
        Item {
            id: clipItem
            required property var modelData
            x: timeline.xAt(modelData.start)
            y: modelData.lane==="audio" ? timeline.audioLaneY : 38
            width: Math.max(1,(modelData.end-modelData.start)/timeline.secondsPerPixel-2)
            height: modelData.lane==="audio" ? timeline.audioLaneHeight : 53
            z: modelData.selected ? .5 : .25
            MouseArea {
                id: clipMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                preventStealing: true
                property bool moved: false
                property var moving: []
                onPressed: function(mouse) {
                    timeline.followEnabled=false
                    timeline.interacted()
                    moved=false
                    moving=preview.movingClips(modelData.index)
                    timeline.pressX=mapToItem(timeline,mouse.x,mouse.y).x
                    timeline.pressView=timeline.viewStart
                    timeline.originalStart=modelData.start
                }
                onPositionChanged: function(mouse) {
                    if (!pressed) return
                    let x=mapToItem(timeline,mouse.x,mouse.y).x
                    if (!moved && Math.abs(x-timeline.pressX)<4) return
                    moved=true
                    if (!moving.length) return
                    timeline.dragIndex=modelData.index
                    timeline.dragClips=moving
                    let raw=timeline.originalStart+(x-timeline.pressX)*timeline.secondsPerPixel+timeline.viewStart-timeline.pressView
                    timeline.dragStart=preview.moveTarget(modelData.index,raw,timeline.secondsPerPixel,Boolean(mouse.modifiers & Qt.AltModifier))
                }
                onReleased: function(mouse) {
                    if (moved && timeline.dragIndex>=0) {
                        let index=modelData.index
                        let target=timeline.dragStart
                        timeline.dragIndex=-1
                        timeline.interacted()
                        preview.moveClip(index,target)
                    }
                }
                onCanceled: timeline.dragIndex=-1
                onClicked: function(mouse) { if (!moved) { timeline.interacted(); preview.selectClip(modelData.index,Boolean(mouse.modifiers & Qt.ControlModifier),Boolean(mouse.modifiers & Qt.ShiftModifier)) } }
                onDoubleClicked: function(mouse) {
                    if (moved) return
                    timeline.interacted()
                    const x = mapToItem(timeline,mouse.x,mouse.y).x
                    preview.beginScrub()
                    preview.endScrub(timeline.positionAt(x,mouse.modifiers))
                }
            }
            ToolTip.visible: clipMouse.containsMouse && !clipMouse.pressed
            ToolTip.delay: 700
            ToolTip.text: modelData.label+" · "+modelData.rangeText+" · Duration "+modelData.durationText+(modelData.lane==="audio" ? "\nShift+wheel: waveform display zoom (1–256×). Listening and export volume unchanged." : "")+(preview.visualsStatus ? "\n"+preview.visualsStatus : "")
        }
    }
    // Every trim edge remains reachable above both selected and unselected bodies.
    Item {
        objectName: "timelineTrimEdges"
        anchors.fill: parent
        z: 1.5
        Repeater {
            model: preview.clips
            Item {
                id: clipEdges
                required property var modelData
                objectName: "clip-edges-"+modelData.index
                x: timeline.xAt(modelData.start)
                y: modelData.lane==="audio" ? timeline.audioLaneY : 38
                width: Math.max(1,(modelData.end-modelData.start)/timeline.secondsPerPixel-2)
                height: modelData.lane==="audio" ? timeline.audioLaneHeight : 53
                Repeater {
                    model: ["left","right"]
                    Rectangle {
                        id: edge
                        required property string modelData
                        objectName: "trim-"+modelData+"-"+clipEdges.modelData.index
                        x: modelData==="left" ? 0 : clipEdges.width-width
                        y: 0; height: clipEdges.height
                        width: Math.min(8,clipEdges.width/3)
                        color: edgeMouse.containsMouse || edgeMouse.pressed ? "#99216baf" : clipEdges.modelData.selected ? "#55216baf" : "transparent"
                        radius: 2
                        HoverHandler {
                            cursorShape: Qt.SizeHorCursor
                        }
                        MouseArea {
                            id: edgeMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.SizeHorCursor
                            preventStealing: true
                            onPressed: function(mouse) {
                                timeline.followEnabled=false
                                timeline.interacted()
                                preview.movingClips(clipEdges.modelData.index)
                                let x=mapToItem(timeline,mouse.x,mouse.y).x
                                timeline.pressX=x; timeline.pressView=timeline.viewStart
                                timeline.resizeMoved=false
                                timeline.resizeIndex=clipEdges.modelData.index
                                timeline.resizeSide=edge.modelData
                                timeline.resizeOriginalEdge=edge.modelData==="left" ? clipEdges.modelData.start : clipEdges.modelData.end
                                timeline.resizeStart=clipEdges.modelData.start; timeline.resizeEnd=clipEdges.modelData.end
                                timeline.resizeMouseX=x; timeline.resizeModifiers=mouse.modifiers
                            }
                            onPositionChanged: function(mouse) { if (pressed) timeline.updateResize(mapToItem(timeline,mouse.x,mouse.y).x,mouse.modifiers) }
                            onReleased: function(mouse) {
                                timeline.updateResize(mapToItem(timeline,mouse.x,mouse.y).x,mouse.modifiers)
                                let index=timeline.resizeIndex
                                let side=timeline.resizeSide
                                let target=side==="left" ? timeline.resizeStart : timeline.resizeEnd
                                let moved=timeline.resizeMoved
                                timeline.resizeIndex=-1
                                timeline.resizeMoved=false
                                timeline.interacted()
                                if (moved) preview.resizeClip(index,side,target)
                            }
                            onCanceled: { timeline.resizeIndex=-1; timeline.resizeMoved=false }
                        }
                    }
                }
            }
        }
    }
    // Draw both outlines above the opaque clip contents.
    // This layer has no input handlers, so the existing timeline gestures stay active.
    Item {
        anchors.fill: parent
        z: 1
        Repeater {
            model: preview.clips
            Rectangle {
                required property var modelData
                objectName: "clip-outline-"+modelData.index
                visible: timeline.overlaps.some(function(overlap) { return overlap.left===modelData.index || overlap.right===modelData.index })
                x: timeline.xAt(modelData.start)
                y: modelData.lane==="audio" ? timeline.audioLaneY : 38
                width: Math.max(1,(modelData.end-modelData.start)/timeline.secondsPerPixel-2)
                height: modelData.lane==="audio" ? timeline.audioLaneHeight : 53
                z: modelData.selected ? 1 : 0
                radius: 4; color: "transparent"
                border.color: modelData.selected ? theme.accent : "#88758aa5"
                border.width: modelData.selected ? 3 : 1
                opacity: timeline.isDragging(modelData.index) || (timeline.resizeIndex>=0 && (preview.lanesLinked ? timeline.resizeIndex%1000000===modelData.index%1000000 : timeline.resizeIndex===modelData.index)) ? .4 : 1
            }
        }
    }
    Repeater {
        model: timeline.dragIndex>=0 ? timeline.dragClips : []
        Rectangle {
            required property var modelData
            z: 2
            objectName: "drag-preview-"+modelData.index
            x: timeline.xAt(modelData.start+timeline.dragStart-timeline.originalStart); y: modelData.lane==="audio" ? timeline.audioLaneY : 38
            width: Math.max(2,(modelData.end-modelData.start)/timeline.secondsPerPixel-2); height: modelData.lane==="audio" ? timeline.audioLaneHeight : 53
            color: "#88216baf"; border.color: theme.accent; border.width: 2; radius: 4
        }
    }
    Repeater {
        model: timeline.resizeIndex<0 ? [] : preview.lanesLinked && preview.hasAudio ? [timeline.resizeIndex%1000000,timeline.resizeIndex%1000000+1000000] : [timeline.resizeIndex]
        Rectangle {
            required property int modelData
            z: 2
            x: timeline.xAt(timeline.resizeStart); y: modelData>=1000000 ? timeline.audioLaneY : 38
            width: Math.max(2,(timeline.resizeEnd-timeline.resizeStart)/timeline.secondsPerPixel-2)
            height: modelData>=1000000 ? timeline.audioLaneHeight : 53; radius: 4; color: "#88216baf"; border.color: theme.accent; border.width: 2
        }
    }
    Item {
        id: playhead
        z: 3
        objectName: "timelinePlayhead"
        readonly property color color: timeline.followEnabled ? theme.followPlayhead : theme.playhead
        x: timeline.xAt(preview.position); y: 24; width: 2; height: preview.hasAudio ? timeline.audioLaneY+timeline.audioLaneHeight-20 : 72
        readonly property real pixelRatio: Screen.devicePixelRatio
        readonly property real pixelFraction: {
            const physicalX = (timeline.mapToItem(null,0,0).x+x)*pixelRatio
            return physicalX-Math.floor(physicalX)
        }
        // Explicit edge coverage preserves subpixel movement on every renderer.
        Rectangle {
            x: -playhead.pixelFraction/playhead.pixelRatio
            width: 1/playhead.pixelRatio; height: parent.height
            color: playhead.color; opacity: 1-playhead.pixelFraction
        }
        Rectangle {
            x: (1-playhead.pixelFraction)/playhead.pixelRatio
            width: playhead.width-1/playhead.pixelRatio; height: parent.height; color: playhead.color
        }
        Rectangle {
            x: playhead.width-playhead.pixelFraction/playhead.pixelRatio
            width: 1/playhead.pixelRatio; height: parent.height
            color: playhead.color; opacity: playhead.pixelFraction
        }
        Rectangle { x: -5; y: -5; width: 12; height: 13; radius: 2; color: playhead.color }
    }
    ScrollBar {
        id: scroll
        objectName: "timelineScrollBar"
        x: timeline.inset; y: preview.hasAudio ? timeline.audioLaneY+timeline.audioLaneHeight+10 : 100; width: timeline.span; height: 12
        orientation: Qt.Horizontal
        visible: timeline.visibleDuration<timeline.totalDuration-.000001
        policy: ScrollBar.AlwaysOn
        minimumSize: Math.min(1,20/Math.max(1,width))
        size: timeline.visibleDuration/timeline.totalDuration
        onPressedChanged: if (pressed) timeline.followEnabled=false
        onPositionChanged: if (pressed) timeline.viewStart=timeline.clampView(position*timeline.totalDuration)
        Binding { target: scroll; property: "position"; value: timeline.clampView(timeline.viewStart)/timeline.totalDuration; when: !scroll.pressed; restoreMode: Binding.RestoreNone }
    }
    Label {
        visible: preview.hasAudio
        anchors.right: parent.right; anchors.rightMargin: timeline.inset+6
        y: timeline.audioLaneY+3
        text: "Waveform ×"+timeline.waveformGain.toFixed(timeline.waveformGain<10 ? 1 : 0)
        font.pixelSize: 10; color: theme.muted
        background: Rectangle { color: theme.caption; radius: 2 }
    }
    function handleWheel(wheel,x,y,horizontal) {
        const pixels = wheel.pixelDelta
        const angles = wheel.angleDelta
        if (horizontal !== Boolean(pixels.x || angles.x)) { wheel.accepted=false; return }
        const steps = (angles.y || angles.x)/120 || (pixels.y || pixels.x)/40
        if (dragIndex>=0 || resizeIndex>=0) { wheel.accepted=false; return }
        if (wheel.modifiers & Qt.ControlModifier) {
            zoom(Math.pow(1.35,steps),x)
        } else if ((wheel.modifiers & Qt.ShiftModifier) && preview.hasAudio && y>=audioLaneY && y<audioLaneY+audioLaneHeight) {
            waveformGain=Math.max(1,Math.min(256,waveformGain*Math.pow(1.35,steps)))
        } else if (pixels.x || pixels.y) {
            followEnabled=false
            viewStart=clampView(viewStart-(pixels.x || pixels.y)*secondsPerPixel)
        } else {
            pan((angles.x || angles.y)/120)
        }
        wheel.accepted=true
    }
    WheelHandler {
        id: verticalWheel
        target: null
        orientation: Qt.Vertical
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function(wheel) { timeline.handleWheel(wheel,verticalWheel.point.position.x,verticalWheel.point.position.y,false) }
    }
    WheelHandler {
        id: horizontalWheel
        target: null
        orientation: Qt.Horizontal
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function(wheel) { timeline.handleWheel(wheel,horizontalWheel.point.position.x,horizontalWheel.point.position.y,true) }
    }
}
