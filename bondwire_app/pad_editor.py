from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from .main_window import MainWindow


class ManualPadEditorDialog(QDialog):
    """Modeless editor for creating and arranging manual PCB pads."""

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("PCB PAD 生成与编辑")
        self.setModal(False)
        self.resize(520, 690)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "生成模式用于按 ΔPAD、ΔX、ΔY 放置；PAD 编号支持负号，例如 -1、PAD-01。"
            "编辑模式用于修改、拖动、对齐和分布所选手工 PAD。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("操作"))
        self.operation_mode = QComboBox()
        self.operation_mode.addItem("生成 PAD", "generate")
        self.operation_mode.addItem("编辑所选 PAD", "edit")
        self.operation_mode.setCurrentIndex(1)
        self.operation_mode.currentIndexChanged.connect(self._update_mode)
        mode_row.addWidget(self.operation_mode, 1)
        layout.addLayout(mode_row)

        properties = QGroupBox("PAD 参数")
        form = QFormLayout(properties)
        self.pad_number = QLineEdit("1")
        self.pad_unit = QComboBox()
        self.pad_unit.addItems(["mil", "mm"])
        self.pad_x = self._double_spin(-100000, 100000, 0.0, 4)
        self.pad_y = self._double_spin(-100000, 100000, 0.0, 4)
        self.pad_width = self._double_spin(0.01, 100000, 20.0, 3)
        self.pad_height = self._double_spin(0.01, 100000, 8.0, 3)
        self.pad_rotation = self._double_spin(-360, 360, 0.0, 2)
        self.pad_rotation.setSuffix(" deg")
        self.pad_shape = QComboBox()
        self.pad_shape.addItems(["roundrect", "rect", "round", "octagon"])
        self.pad_color_button = QPushButton()
        form.addRow("起始编号", self.pad_number)
        form.addRow("单位", self.pad_unit)
        form.addRow("起始 X", self.pad_x)
        form.addRow("起始 Y", self.pad_y)
        form.addRow("宽度", self.pad_width)
        form.addRow("高度", self.pad_height)
        form.addRow("旋转", self.pad_rotation)
        form.addRow("形状", self.pad_shape)
        form.addRow("颜色", self.pad_color_button)
        layout.addWidget(properties)

        step_group = QGroupBox("批量步进（生成和多选编辑）")
        step_form = QFormLayout(step_group)
        self.pad_count = QSpinBox()
        self.pad_count.setRange(1, 10000)
        self.pad_count.setValue(1)
        self.delta_pad_enabled = QCheckBox("启用编号步进")
        self.delta_pad = QSpinBox()
        self.delta_pad.setRange(-100000, 100000)
        self.delta_pad.setValue(1)
        self.delta_pad.setPrefix("ΔPAD = ")
        self.delta_x_enabled = QCheckBox("启用 X 轴步进")
        self.delta_x = self._double_spin(-100000, 100000, 0.0, 4)
        self.delta_y_enabled = QCheckBox("启用 Y 轴步进")
        self.delta_y = self._double_spin(-100000, 100000, 0.0, 4)
        delta_pad_row = QHBoxLayout()
        delta_pad_row.addWidget(self.delta_pad_enabled)
        delta_pad_row.addWidget(self.delta_pad, 1)
        delta_x_row = QHBoxLayout()
        delta_x_row.addWidget(self.delta_x_enabled)
        delta_x_row.addWidget(self.delta_x, 1)
        delta_y_row = QHBoxLayout()
        delta_y_row.addWidget(self.delta_y_enabled)
        delta_y_row.addWidget(self.delta_y, 1)
        step_form.addRow("生成数量", self.pad_count)
        step_form.addRow(delta_pad_row)
        step_form.addRow(delta_x_row)
        step_form.addRow(delta_y_row)
        layout.addWidget(step_group)

        generation_row = QHBoxLayout()
        self.single_generate_button = QPushButton("生成单个 PAD")
        self.generate_button = QPushButton("批量生成 PAD")
        generation_row.addWidget(self.single_generate_button)
        generation_row.addWidget(self.generate_button)
        layout.addLayout(generation_row)

        action_row = QHBoxLayout()
        self.update_button = QPushButton("更新所选 PAD")
        self.delete_button = QPushButton("删除所选 PAD")
        action_row.addWidget(self.update_button)
        action_row.addWidget(self.delete_button)
        layout.addLayout(action_row)

        arrange_group = QGroupBox("对齐与分布")
        arrange_layout = QVBoxLayout(arrange_group)
        self.pad_spacing = self._double_spin(0.0, 100000, 0.0, 3)
        spacing_form = QFormLayout()
        spacing_form.addRow("等距间距（0=自动）", self.pad_spacing)
        arrange_layout.addLayout(spacing_form)
        align_row = QHBoxLayout()
        for name, mode in (("左", "left"), ("右", "right"), ("上", "top"), ("下", "bottom")):
            button = QPushButton(f"{name}对齐")
            button.clicked.connect(
                lambda _checked=False, current=mode: main_window.align_selected_manual_pads(current)
            )
            align_row.addWidget(button)
        arrange_layout.addLayout(align_row)
        distribute_row = QHBoxLayout()
        distribute_x = QPushButton("水平等距")
        distribute_y = QPushButton("垂直等距")
        distribute_x.clicked.connect(lambda: main_window.distribute_selected_manual_pads("x"))
        distribute_y.clicked.connect(lambda: main_window.distribute_selected_manual_pads("y"))
        distribute_row.addWidget(distribute_x)
        distribute_row.addWidget(distribute_y)
        arrange_layout.addLayout(distribute_row)
        layout.addWidget(arrange_group)

        mode_buttons = QHBoxLayout()
        edit_canvas_button = QPushButton("画布 PAD 编辑模式")
        wire_button = QPushButton("切换到 BondWire 模式")
        edit_canvas_button.clicked.connect(lambda: main_window.set_mode(False))
        wire_button.clicked.connect(lambda: main_window.set_mode(True))
        mode_buttons.addWidget(edit_canvas_button)
        mode_buttons.addWidget(wire_button)
        layout.addLayout(mode_buttons)

        self.pad_unit.currentTextChanged.connect(main_window.change_manual_pad_unit)
        self.pad_color_button.clicked.connect(main_window.choose_manual_pad_color)
        self.single_generate_button.clicked.connect(main_window.add_single_manual_pad_from_controls)
        self.generate_button.clicked.connect(main_window.add_manual_pad_from_controls)
        self.update_button.clicked.connect(main_window.apply_manual_pad_controls_to_selection)
        self.delete_button.clicked.connect(main_window.delete_selected_manual_pads)
        self.delta_pad_enabled.toggled.connect(self.delta_pad.setEnabled)
        self.delta_x_enabled.toggled.connect(self.delta_x.setEnabled)
        self.delta_y_enabled.toggled.connect(self.delta_y.setEnabled)
        self.delta_pad.setEnabled(False)
        self.delta_x.setEnabled(False)
        self.delta_y.setEnabled(False)
        self._update_mode()

    @staticmethod
    def _double_spin(minimum: float, maximum: float, value: float, decimals: int) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setValue(value)
        box.setSingleStep(0.1)
        return box

    def mode(self) -> str:
        return str(self.operation_mode.currentData())

    def set_mode(self, mode: str) -> None:
        index = self.operation_mode.findData(mode)
        if index >= 0:
            self.operation_mode.setCurrentIndex(index)
        self._update_mode()

    def _update_mode(self, _index: int | None = None) -> None:
        generating = self.mode() == "generate"
        self.pad_count.setEnabled(generating)
        self.single_generate_button.setEnabled(generating)
        self.generate_button.setEnabled(generating)
        self.update_button.setEnabled(not generating)
        self.delete_button.setEnabled(not generating)
        if not generating and hasattr(self.main_window, "pad_editor_dialog"):
            self.main_window.sync_manual_pad_controls_from_selection()
