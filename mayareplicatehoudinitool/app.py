import sys

from avalon.vendor.Qt import QtWidgets, QtCore
from avalon.tools import lib as tools_lib

from mayareplicatehoudinitool import lib

module = sys.modules[__name__]
module.window = None

DEFAULT_TARGETS = [
    "position",
    "rampPosition",
    "worldPosition",

    "velocity",
    "rampVelocity",
    "worldVelocity",

    "Acceleration",
    "rampAcceleration",
    "mass",
]

INSTANCER_PP_ATTRIBUTES = {
    "general":[
        "position",
        "scale",
        "shear",
        "objectIndex",
        "visibility"
    ],
    "rotation":[
        "rotation",
        "aimDirection",
        "aimPosition",
        "aimAxis",
        "aimUpAxis",
        "aimWorldUp",
    ]
}


class SearchComboBox(QtWidgets.QComboBox):
    """Searchable ComboBox with empty placeholder value as first value"""

    def __init__(self, parent=None, placeholder=""):
        super(SearchComboBox, self).__init__(parent)

        self.setEditable(True)
        self.setInsertPolicy(self.NoInsert)
        self.lineEdit().setPlaceholderText(placeholder)

        # Apply completer settings
        completer = self.completer()
        completer.setCompletionMode(completer.PopupCompletion)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)

        # Force style sheet on popup menu
        # It won't take the parent stylesheet for some reason
        # todo: better fix for completer popup stylesheet

    def populate(self, items):
        self.clear()
        self.addItems([""])     # ensure first item is placeholder
        self.addItems(items)

    def get_valid_value(self):
        """Return the current text if it's a valid value else None

        Note: The empty placeholder value is valid and returns as ""
        Returns:
            str or None
        """

        text = self.currentText()
        lookup = set(self.itemText(i) for i in range(self.count()))
        if text not in lookup:
            return None

        return text


class App(QtWidgets.QWidget):

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)

        self.setWindowTitle("Replicate Houdini Asset (particles)")
        self.resize(280, 280)

        layout = QtWidgets.QVBoxLayout()

        input_box = QtWidgets.QGroupBox("Input")
        input_box.setStyleSheet("{color: red}")
        input_vboxlayout = QtWidgets.QVBoxLayout()
        from_selection = QtWidgets.QCheckBox("Selected")
        from_selection.setChecked(True)

        name_hlayout = QtWidgets.QHBoxLayout()
        name_label = QtWidgets.QLabel("Name")
        name_field = QtWidgets.QLineEdit()
        name_hlayout.addWidget(name_label)
        name_hlayout.addWidget(name_field)

        input_box.setLayout(input_vboxlayout)
        input_vboxlayout.addWidget(from_selection)
        input_vboxlayout.addLayout(name_hlayout)

        time_box = QtWidgets.QGroupBox("Time")
        time_hlayout = QtWidgets.QHBoxLayout()
        time_start_vbox = QtWidgets.QVBoxLayout()
        time_start_label = QtWidgets.QLabel("Start")
        time_start = QtWidgets.QSpinBox()
        time_start_vbox.addWidget(time_start_label)
        time_start_vbox.addWidget(time_start)

        time_end_vbox = QtWidgets.QVBoxLayout()
        time_end_label = QtWidgets.QLabel("End")
        time_end = QtWidgets.QSpinBox()
        time_end_vbox.addWidget(time_end_label)
        time_end_vbox.addWidget(time_end)

        time_hlayout.addLayout(time_start_vbox)
        time_hlayout.addLayout(time_end_vbox)
        time_box.setLayout(time_hlayout)

        mapping_box = QtWidgets.QGroupBox("Attribute mapping")
        mapping_layout = QtWidgets.QVBoxLayout()
        mapping_box.setLayout(mapping_layout)

        button_vlayout = QtWidgets.QVBoxLayout()
        replicate = QtWidgets.QPushButton("Replicate")
        update_hlayout = QtWidgets.QHBoxLayout()
        update_all_button = QtWidgets.QPushButton("Update All")
        update_selected_button = QtWidgets.QPushButton("Update Selected")
        update_hlayout.addWidget(update_all_button)
        update_hlayout.addWidget(update_selected_button)

        refresh_button = QtWidgets.QPushButton("Refresh")

        button_vlayout.addWidget(replicate)
        button_vlayout.addLayout(update_hlayout)
        button_vlayout.addWidget(refresh_button)

        layout.addWidget(input_box)
        # layout.addWidget(time_box)
        layout.addWidget(mapping_box)
        layout.addLayout(button_vlayout)

        # Open up items for code
        self._selection = []
        self.mapping_data = {}

        self.from_selection = from_selection
        self.name_field = name_field

        self.time_start = time_start
        self.time_end = time_end

        self.mapping_layout = mapping_layout
        self.replicate_button = replicate
        self.update_all_button = update_all_button
        self.update_selected_button = update_selected_button
        self.refesh_button = refresh_button

        self.setLayout(layout)

        layout.addStretch(True)

        self.get_settings()

        self.connections()

    def connections(self):

        self.replicate_button.clicked.connect(self.process)
        self.update_all_button.clicked.connect(self.update_all)
        self.refesh_button.clicked.connect(self.refresh)

    def refresh(self):
        """Rebuild the attribute mapping"""

        items = self.mapping_layout.count()
        for idx in range(items):
            widget_item = self.mapping_layout.itemAt(idx)
            widget = widget_item.widget()
            widget.deleteLater()

        # Reset mapping data
        self.mapping_data = {}

        self.get_settings()

    def get_settings(self):

        targets = set()
        assets = lib.get_houdini_assets(self.from_selection.isChecked())
        self._selection = assets
        if not assets:
            return

        for asset in assets:
            particle = lib.get_particle_system(asset)
            attrs = lib.get_particle_attributes(particle)
            clean_attrs = [a.split(":")[0] for a in attrs]
            targets.update(clean_attrs)

        targets = DEFAULT_TARGETS + list(targets)
        for section in ["general", "rotation"]:
            attributes = INSTANCER_PP_ATTRIBUTES[section]
            box = self._create_mapper(section, attributes, targets)
            self.mapping_layout.addWidget(box)

    def _create_mapper(self, section, sources, targets):

        section_box = QtWidgets.QGroupBox(section.title())
        section_box.setObjectName(section)

        layout = QtWidgets.QVBoxLayout()
        for source in sources:

            picker_hlayout = QtWidgets.QHBoxLayout()
            source_label = QtWidgets.QLabel(source)

            # Create lookup
            target_picker = SearchComboBox(placeholder="None")
            target_picker.populate(targets)

            picker_hlayout.addWidget(source_label)
            picker_hlayout.addWidget(target_picker)

            layout.addLayout(picker_hlayout)
            self.mapping_data[source] = target_picker

        section_box.setLayout(layout)

        return section_box

    def process(self):

        name = self.name_field.text()
        if not name:
            raise RuntimeError("Name is a required field")

        # Get attribute mapping
        ignored = ["", None]
        mapping = {s: str(p.get_valid_value()) for s, p in
                   self.mapping_data.items() if p.get_valid_value() not
                   in ignored}

        # Add default behavior from Houdini
        for asset in self._selection:
            # Here we pass on the asset and its information
            asset_mapping = lib.map_houdini_asset(asset)
            lib.replicate(name,
                          asset_mapping=asset_mapping,
                          attribute_mapping=mapping)

    def update_all(self):
        assets = lib.get_houdini_assets()
        for asset in assets:
            lib.update_asset(asset)

    def update_selected(self):
        assets = lib.get_houdini_assets(True)
        for asset in assets:
            lib.update_asset(asset)


def show(parent=None):
    """Display Loader GUI

    Arguments:
        debug (bool, optional): Run loader in debug-mode,
            defaults to False

    """

    try:
        module.window.close()
        del module.window
    except (RuntimeError, AttributeError):
        pass

    with tools_lib.application():
        window = App(parent)
        window.show()

        module.window = window