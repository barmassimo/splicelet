import QtQuick

QtObject {
    required property bool dark
    readonly property color window: dark ? "#171c24" : "#f5f7fb"
    readonly property color text: dark ? "#e3eaf3" : "#243248"
    readonly property color muted: dark ? "#a8b6c8" : "#59687b"
    readonly property color surface: dark ? "#252e3b" : "#ffffff"
    readonly property color disabled: dark ? "#75859a" : "#8998aa"
    readonly property color disabledText: dark ? "#8e9eb2" : "#69778a"
    readonly property color accent: dark ? "#74b4f5" : "#1967d9"
    readonly property color line: dark ? "#435267" : "#c1cbd7"
    readonly property color well: dark ? "#202834" : "#ecf2fa"
    readonly property color frame: dark ? "#3b495c" : "#cad4df"
    readonly property color border: dark ? "#354357" : "#e0e7f1"
    readonly property color buttonBorder: dark ? "#435267" : "#dce5f1"
    readonly property color pressed: dark ? "#3b526d" : "#dce8f4"
    readonly property color hover: dark ? "#314259" : "#e9f1f9"
    readonly property color timeline: well
    readonly property color tick: dark ? "#60758f" : "#a7b8cb"
    readonly property color gap: dark ? "#171f2a" : "#dce2e9"
    readonly property color hatch: dark ? "#5c6c81" : "#b8c3cf"
    readonly property color gapBorder: dark ? "#3e4e64" : "#b0bccb"
    readonly property color selected: dark ? "#324d6d" : "#d7e8fc"
    readonly property color clip: dark ? "#293646" : "#f8fafc"
    readonly property color caption: dark ? "#dd253141" : "#ddf8fafc"
    readonly property color wave: dark ? "#91bfd8" : "#4c7892"
    readonly property color playhead: dark ? "#94c9ff" : "#184f82"
    readonly property color followPlayhead: dark ? "#ffbc70" : "#b84f00"
    readonly property color track: dark ? "#435267" : "#d6e0eb"
}
