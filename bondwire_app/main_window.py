from __future__ import annotations

import json
import math
from pathlib import Path

from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QKeySequence, QPainter, QPen
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtWidgets import (
    QAction,
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .graphics import (
    BoardAssemblyItem,
    BoardNativePreviewItem,
    BoardPadItem,
    BondEndpointHandle,
    BondWireItem,
    ChipItem,
    ChipPadHitItem,
    ChipPadLabelItem,
    FreeEndpointMarkerItem,
)
from .loaders import load_gds, load_pcblib
from .models import BoardData, BoardPad, Bond, ChipData, ProjectData
from .simulation import (
    bond_midpoint,
    bond_control_point,
    midpoint_to_control,
    quadratic_length,
    sample_quadratic,
)
from .three_d import Bond3DDialog


class CanvasView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, click_handler, double_click_handler):
        super().__init__(scene)
        self.click_handler = click_handler
        self.double_click_handler = double_click_handler
        self.wire_mode = False
        self.endpoint_press_pos: QPoint | None = None
        self.endpoint_drag_item: BondEndpointHandle | None = None
        self.endpoint_was_dragged = False
        self.setRenderHint(QPainter.Antialiasing)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#666666"))

    def wheelEvent(self, event) -> None:
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        if self.wire_mode and event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            current = item
            while current is not None:
                if isinstance(current, BondEndpointHandle):
                    self.endpoint_press_pos = event.pos()
                    self.endpoint_drag_item = current
                    self.endpoint_was_dragged = False
                    event.accept()
                    return
                current = current.parentItem()
            self.click_handler(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.endpoint_press_pos is not None and self.endpoint_drag_item is not None:
            self.endpoint_was_dragged = self.endpoint_was_dragged or (
                event.pos() - self.endpoint_press_pos
            ).manhattanLength() >= QApplication.startDragDistance()
            if self.endpoint_was_dragged:
                parent = self.endpoint_drag_item.parentItem()
                self.endpoint_drag_item.setPos(parent.mapFromScene(self.mapToScene(event.pos())))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        endpoint_press = self.endpoint_press_pos is not None and self.endpoint_drag_item is not None
        was_dragged = self.endpoint_was_dragged
        if endpoint_press:
            if not was_dragged and event.button() == Qt.LeftButton:
                self.click_handler(self.mapToScene(event.pos()))
            self.endpoint_press_pos = None
            self.endpoint_drag_item = None
            self.endpoint_was_dragged = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self.wire_mode and event.button() == Qt.LeftButton:
            self.double_click_handler(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def scene_tolerance(self, pixels: int = 12) -> float:
        p0 = self.mapToScene(QPoint(0, 0))
        p1 = self.mapToScene(QPoint(pixels, 0))
        return abs(p1.x() - p0.x())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GDS BondWire Planner")
        self.resize(1450, 900)

        self.project = ProjectData()
        self.project_path = ""
        self.board: BoardData | None = None
        self.chip: ChipData | None = None
        self.board_assembly_item: BoardAssemblyItem | None = None
        self.board_preview_item: BoardNativePreviewItem | None = None
        self.board_items: dict[str, BoardPadItem] = {}
        self.chip_item: ChipItem | None = None
        self.bond_items: list[BondWireItem] = []
        self.pending_endpoint: tuple[str, str] | None = None
        self.pending_free_pos: QPointF | None = None
        self.pending_free_item: FreeEndpointMarkerItem | None = None
        self.updating_transform = False
        self.three_d_dialog: Bond3DDialog | None = None

        self.scene = QGraphicsScene(self)
        self.view = CanvasView(self.scene, self.handle_canvas_click, self.handle_canvas_double_click)
        self._build_ui()
        self._build_toolbar()
        self._draw_origin()
        self.statusBar().showMessage("请打开 PcbLib 和 GDS 文件。")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        actions = [
            ("打开 PcbLib", self.choose_pcblib),
            ("打开 GDS", self.choose_gds),
            ("打开工程", self.choose_open_project),
            ("保存工程", self.choose_save_project),
            ("适合窗口", self.fit_scene),
            ("删除打线", self.delete_selected_bonds),
            ("导出 PDF", self.choose_export_pdf),
            ("导出 AD26 脚本", self.choose_export_ad26_script),
        ]
        for name, callback in actions:
            action = QAction(name, self)
            action.triggered.connect(callback)
            if name == "删除打线":
                action.setShortcut(QKeySequence.Delete)
            toolbar.addAction(action)

        toolbar.addSeparator()
        action = QAction("3D 视图", self)
        action.triggered.connect(self.show_3d_view)
        toolbar.addAction(action)

        toolbar.addSeparator()
        self.move_action = QAction("移动芯片", self)
        self.move_action.setCheckable(True)
        self.move_action.setChecked(True)
        self.move_action.triggered.connect(lambda: self.set_mode(False))
        toolbar.addAction(self.move_action)

        self.wire_action = QAction("绘制 BondWire", self)
        self.wire_action.setCheckable(True)
        self.wire_action.triggered.connect(lambda: self.set_mode(True))
        toolbar.addAction(self.wire_action)

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.view)
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel.setMinimumWidth(500)
        panel.setMaximumWidth(760)
        panel_splitter = QSplitter(Qt.Vertical)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setWidget(controls)

        file_group = QGroupBox("文件与识别结果")
        file_form = QFormLayout(file_group)
        self.pcb_label = QLabel("未加载")
        self.gds_label = QLabel("未加载")
        self.pcb_info = QLabel("-")
        self.gds_info = QLabel("-")
        for label in (self.pcb_label, self.gds_label, self.pcb_info, self.gds_info):
            label.setWordWrap(True)
        file_form.addRow("PcbLib", self.pcb_label)
        file_form.addRow("PCB PAD", self.pcb_info)
        file_form.addRow("GDS", self.gds_label)
        file_form.addRow("芯片 PAD", self.gds_info)
        controls_layout.addWidget(file_group)

        layer_group = QGroupBox("GDS 层映射")
        layer_form = QFormLayout(layer_group)
        self.cb_layer = self._int_spin(0, 65535, 76)
        self.cb_datatype = self._int_spin(0, 65535, 0)
        self.ap_layer = self._int_spin(0, 65535, 126)
        self.ap_texttype = self._int_spin(0, 65535, 0)
        self.search_depth = self._int_spin(0, 100, 10)
        reload_button = QPushButton("按层映射重新识别")
        reload_button.clicked.connect(self.reload_gds)
        layer_form.addRow("CB Drawing Layer", self.cb_layer)
        layer_form.addRow("CB Drawing Datatype", self.cb_datatype)
        layer_form.addRow("AP Pin Layer", self.ap_layer)
        layer_form.addRow("AP Pin Texttype", self.ap_texttype)
        layer_form.addRow("PAD 搜索深度", self.search_depth)
        layer_form.addRow(reload_button)
        controls_layout.addWidget(layer_group)

        transform_group = QGroupBox("芯片位置（mil）")
        transform_form = QFormLayout(transform_group)
        self.chip_x = self._double_spin(-100000, 100000, 0.0, 4)
        self.chip_y = self._double_spin(-100000, 100000, 0.0, 4)
        self.chip_rotation = self._double_spin(-360, 360, 0.0, 2)
        self.chip_x.valueChanged.connect(self.apply_transform_controls)
        self.chip_y.valueChanged.connect(self.apply_transform_controls)
        self.chip_rotation.valueChanged.connect(self.apply_transform_controls)
        transform_form.addRow("X", self.chip_x)
        transform_form.addRow("Y", self.chip_y)
        transform_form.addRow("旋转角度", self.chip_rotation)
        controls_layout.addWidget(transform_group)

        pcb_transform_group = QGroupBox("PCB 封装变换")
        pcb_transform_form = QFormLayout(pcb_transform_group)
        self.pcb_rotation = self._double_spin(-360, 360, 0.0, 2)
        self.pcb_rotation.valueChanged.connect(self.apply_pcb_transform)
        pcb_transform_form.addRow("旋转角度", self.pcb_rotation)
        controls_layout.addWidget(pcb_transform_group)

        footprint_group = QGroupBox("封装绘制（手工 PCB PAD）")
        footprint_layout = QVBoxLayout(footprint_group)
        footprint_form = QFormLayout()
        self.manual_pad_number = QLineEdit("1")
        self.manual_pad_width = self._double_spin(0.01, 100000, 20.0, 3)
        self.manual_pad_height = self._double_spin(0.01, 100000, 8.0, 3)
        self.manual_pad_rotation = self._double_spin(-360, 360, 0.0, 2)
        self.manual_pad_shape = QComboBox()
        self.manual_pad_shape.addItems(["roundrect", "rect", "round", "octagon"])
        for box in (self.manual_pad_width, self.manual_pad_height):
            box.setSuffix(" mil")
            box.setSingleStep(1.0)
        self.manual_pad_rotation.setSuffix(" deg")
        footprint_form.addRow("编号", self.manual_pad_number)
        footprint_form.addRow("宽度", self.manual_pad_width)
        footprint_form.addRow("高度", self.manual_pad_height)
        footprint_form.addRow("旋转", self.manual_pad_rotation)
        footprint_form.addRow("形状", self.manual_pad_shape)
        footprint_layout.addLayout(footprint_form)

        manual_button_row = QHBoxLayout()
        add_pad_button = QPushButton("添加 PAD")
        add_pad_button.clicked.connect(self.add_manual_pad_from_controls)
        delete_pad_button = QPushButton("删除手工 PAD")
        delete_pad_button.clicked.connect(self.delete_selected_manual_pads)
        manual_button_row.addWidget(add_pad_button)
        manual_button_row.addWidget(delete_pad_button)
        footprint_layout.addLayout(manual_button_row)

        align_row = QHBoxLayout()
        for name, mode in (
            ("左对齐", "left"),
            ("右对齐", "right"),
            ("上对齐", "top"),
            ("下对齐", "bottom"),
        ):
            button = QPushButton(name)
            button.clicked.connect(lambda _checked=False, current=mode: self.align_selected_manual_pads(current))
            align_row.addWidget(button)
        footprint_layout.addLayout(align_row)

        distribute_row = QHBoxLayout()
        distribute_x = QPushButton("水平等距")
        distribute_y = QPushButton("垂直等距")
        distribute_x.clicked.connect(lambda: self.distribute_selected_manual_pads("x"))
        distribute_y.clicked.connect(lambda: self.distribute_selected_manual_pads("y"))
        distribute_row.addWidget(distribute_x)
        distribute_row.addWidget(distribute_y)
        footprint_layout.addLayout(distribute_row)
        controls_layout.addWidget(footprint_group)

        wire_group = QGroupBox("打线样式与 PDF")
        wire_form = QFormLayout(wire_group)
        self.wire_color_button = QPushButton()
        self.wire_color_button.clicked.connect(self.choose_wire_color)
        self.wire_width = self._double_spin(0.01, 10.0, self.project.bondwire_width_mil, 3)
        self.wire_width.setSingleStep(0.05)
        self.wire_width.setSuffix(" mil")
        self.wire_width.valueChanged.connect(self.apply_wire_style)
        self.pdf_include_labels = QCheckBox("导出 PDF 时包含芯片 PAD 标签")
        self.pdf_include_labels.setChecked(self.project.pdf_include_chip_pad_labels)
        self.pdf_include_labels.toggled.connect(self.update_pdf_label_option)
        self._update_wire_color_button()
        wire_form.addRow("BondWire 颜色", self.wire_color_button)
        wire_form.addRow("BondWire 粗细", self.wire_width)
        wire_form.addRow(self.pdf_include_labels)
        controls_layout.addWidget(wire_group)

        self.instruction = QLabel(
            "操作：切换到“绘制 BondWire”后点击 PAD；双击非 PAD 区域可创建自由连接端点。"
        )
        self.instruction.setWordWrap(True)
        controls_layout.addWidget(self.instruction)
        controls_layout.addStretch(1)

        endpoint_group = QGroupBox("打线端点列表")
        endpoint_layout = QVBoxLayout(endpoint_group)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "端点 A", "端点 B", "3D 长度/mil"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setMinimumHeight(260)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._sync_3d_selection_from_table)
        endpoint_layout.addWidget(self.table, 1)

        button_row = QHBoxLayout()
        delete_button = QPushButton("删除所选")
        delete_button.clicked.connect(self.delete_selected_bonds)
        clear_button = QPushButton("清空全部")
        clear_button.clicked.connect(self.clear_bonds)
        button_row.addWidget(delete_button)
        button_row.addWidget(clear_button)
        endpoint_layout.addLayout(button_row)

        panel_splitter.addWidget(controls_scroll)
        panel_splitter.addWidget(endpoint_group)
        panel_splitter.setStretchFactor(0, 0)
        panel_splitter.setStretchFactor(1, 1)
        panel_splitter.setSizes([430, 380])
        panel_layout.addWidget(panel_splitter)
        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([920, 530])
        self.setCentralWidget(splitter)

    @staticmethod
    def _int_spin(minimum: int, maximum: int, value: int) -> QSpinBox:
        box = QSpinBox()
        box.setRange(minimum, maximum)
        box.setValue(value)
        return box

    @staticmethod
    def _double_spin(minimum: float, maximum: float, value: float, decimals: int) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setValue(value)
        box.setSingleStep(0.1)
        return box

    def _draw_origin(self) -> None:
        pen = QPen(QColor(130, 145, 160, 120), 0, Qt.DashLine)
        self.scene.addLine(-3, 0, 3, 0, pen).setZValue(1)
        self.scene.addLine(0, -3, 0, 3, pen).setZValue(1)

    def set_mode(self, wire_mode: bool) -> None:
        self.view.wire_mode = wire_mode
        self.wire_action.setChecked(wire_mode)
        self.move_action.setChecked(not wire_mode)
        self._set_pending_endpoint(None)
        self.view.setDragMode(QGraphicsView.NoDrag)
        self.view.setCursor(Qt.CrossCursor if wire_mode else Qt.ArrowCursor)
        if self.chip_item:
            self.chip_item.set_interactive(not wire_mode)
        self.statusBar().showMessage(
            "打线模式：点击 PAD 或双击非 PAD 区域建立连接；拖动圆形端点可微调落点。"
            if wire_mode
            else "移动模式：拖动芯片，滚轮缩放。"
        )

    def choose_wire_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.project.bondwire_color), self, "选择 BondWire 颜色")
        if not color.isValid():
            return
        self.project.bondwire_color = color.name()
        self._update_wire_color_button()
        self.apply_wire_style()

    def _update_wire_color_button(self) -> None:
        color = QColor(self.project.bondwire_color)
        text_color = "#000000" if color.lightness() > 145 else "#ffffff"
        self.wire_color_button.setText(self.project.bondwire_color.upper())
        self.wire_color_button.setStyleSheet(
            f"QPushButton {{ background-color: {self.project.bondwire_color}; color: {text_color}; "
            "font-weight: bold; min-height: 24px; }"
        )

    def apply_wire_style(self) -> None:
        self.project.bondwire_width_mil = self.wire_width.value()
        for item in self.bond_items:
            item.set_style(self.project.bondwire_color, self.project.bondwire_width_mil)

    def update_pdf_label_option(self, checked: bool) -> None:
        self.project.pdf_include_chip_pad_labels = checked

    def choose_pcblib(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 Altium PcbLib", "", "Altium PcbLib (*.PcbLib)")
        if path:
            self.load_pcblib_file(path)

    def choose_gds(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 GDSII", "", "GDSII (*.gds *.gdsii)")
        if path:
            self.load_gds_file(path)

    def load_pcblib_file(self, path: str) -> None:
        try:
            board = load_pcblib(path)
        except Exception as exc:
            self._show_error("PcbLib 读取失败", exc)
            return
        if self.board_assembly_item:
            self.scene.removeItem(self.board_assembly_item)
            self.board_assembly_item = None
            self.board_preview_item = None
        self.board_items.clear()
        self.board = board
        self.project.pcb_path = board.path
        self.board_assembly_item = BoardAssemblyItem()
        self.scene.addItem(self.board_assembly_item)
        if board.preview_svg and board.preview_bbox_mil:
            self.board_preview_item = BoardNativePreviewItem(board.preview_svg, board.preview_bbox_mil)
            self.board_preview_item.setParentItem(self.board_assembly_item)
        for pad in board.pads:
            self._add_board_pad_item(pad, native_rendered=self.board_preview_item is not None)
        self._render_manual_board_pads()
        self.apply_pcb_transform()
        self.pcb_label.setText(Path(board.path).name)
        self._update_pcb_info()
        self.clear_bonds()
        self.fit_scene()

    def apply_pcb_transform(self) -> None:
        rotation = self.pcb_rotation.value()
        self.project.pcb_rotation_deg = rotation
        if self.board_assembly_item is not None:
            self.board_assembly_item.setRotation(rotation)
        self.update_bond_items()

    def board_scene_point(self, x_mil: float, y_mil: float) -> QPointF:
        local = QPointF(x_mil, y_mil)
        if self.board_assembly_item is None:
            return local
        return self.board_assembly_item.mapToScene(local)

    def _ensure_board_container(self) -> None:
        if self.board is None:
            self.board = BoardData(path="", footprint_name="Manual_Footprint")
            self.pcb_label.setText("手工封装")
        if self.board_assembly_item is None:
            self.board_assembly_item = BoardAssemblyItem()
            self.scene.addItem(self.board_assembly_item)
            self.apply_pcb_transform()

    def _add_board_pad_item(self, pad: BoardPad, native_rendered: bool = False) -> BoardPadItem:
        self._ensure_board_container()
        item = BoardPadItem(
            pad,
            native_rendered=native_rendered and not pad.manual,
            changed=self.manual_board_pad_changed if pad.manual else None,
        )
        item.setParentItem(self.board_assembly_item)
        self.board_items[pad.number] = item
        return item

    def _render_manual_board_pads(self) -> None:
        self._ensure_board_container()
        for pad in self.project.manual_board_pads:
            pad.manual = True
            if pad.number not in self.board_items:
                self._add_board_pad_item(pad, native_rendered=False)
        self._sync_manual_board_pads()

    def _sync_manual_board_pads(self) -> None:
        manual_pads = [
            item.pad
            for item in self.board_items.values()
            if item.pad.manual
        ]
        self.project.manual_board_pads = manual_pads
        if self.board is not None:
            imported = [pad for pad in self.board.pads if not pad.manual]
            self.board.pads = imported + manual_pads

    def _update_pcb_info(self) -> None:
        if not self.board:
            self.pcb_info.setText("-")
            return
        manual_count = len(self.project.manual_board_pads)
        imported_count = max(0, len(self.board.pads) - manual_count)
        self.pcb_info.setText(
            f"{self.board.footprint_name}，识别 {imported_count} 个封装 PAD、"
            f"手工 {manual_count} 个 PAD、{self.board.native_primitive_count} 个原始封装图元；"
            f"金属层：{', '.join(self.board.metal_layers) or '无'}"
        )

    def _next_manual_pad_number(self) -> str:
        numbers = []
        for name in self.board_items:
            try:
                numbers.append(int(name))
            except ValueError:
                continue
        return str(max(numbers, default=0) + 1)

    def _selected_manual_pad_items(self) -> list[BoardPadItem]:
        seen: set[int] = set()
        selected: list[BoardPadItem] = []
        for item in self.scene.selectedItems():
            current = item
            while current is not None:
                if isinstance(current, BoardPadItem) and current.pad.manual:
                    item_id = id(current)
                    if item_id not in seen:
                        seen.add(item_id)
                        selected.append(current)
                    break
                current = current.parentItem()
        return selected

    def manual_board_pad_changed(self, _item: BoardPadItem) -> None:
        self._sync_manual_board_pads()
        self.update_bond_items()
        self._update_pcb_info()

    def add_manual_pad_from_controls(self) -> None:
        number = self.manual_pad_number.text().strip()
        if not number:
            self.statusBar().showMessage("请输入 PAD 编号。")
            return
        if number in self.board_items:
            self.statusBar().showMessage(f"PAD {number} 已存在，请换一个编号。")
            return
        self._ensure_board_container()
        scene_pos = self.view.mapToScene(self.view.viewport().rect().center())
        local_pos = (
            self.board_assembly_item.mapFromScene(scene_pos)
            if self.board_assembly_item is not None
            else scene_pos
        )
        pad = BoardPad(
            number=number,
            x_mil=local_pos.x(),
            y_mil=local_pos.y(),
            width_mil=self.manual_pad_width.value(),
            height_mil=self.manual_pad_height.value(),
            rotation_deg=self.manual_pad_rotation.value(),
            shape=self.manual_pad_shape.currentText(),
            corner_radius_percent=50.0,
            manual=True,
        )
        self.project.manual_board_pads.append(pad)
        self._add_board_pad_item(pad)
        self._sync_manual_board_pads()
        self._update_pcb_info()
        self.manual_pad_number.setText(self._next_manual_pad_number())
        self.statusBar().showMessage(f"已添加手工 PCB PAD {number}，可在移动模式下拖动它。")

    def delete_selected_manual_pads(self) -> None:
        selected = self._selected_manual_pad_items()
        if not selected:
            self.statusBar().showMessage("请先选择需要删除的手工 PAD。")
            return
        deleted = {item.pad.number for item in selected}
        for item in selected:
            self.scene.removeItem(item)
            self.board_items.pop(item.pad.number, None)
        self.project.bonds = [
            bond
            for bond in self.project.bonds
            if not (bond.board_endpoint_type == "pad" and bond.board_pad in deleted)
        ]
        self._sync_manual_board_pads()
        self._update_pcb_info()
        self.rebuild_bonds()
        self.statusBar().showMessage(f"已删除 {len(deleted)} 个手工 PAD，并移除相关 BondWire。")

    def align_selected_manual_pads(self, mode: str) -> None:
        selected = self._selected_manual_pad_items()
        if len(selected) < 2:
            self.statusBar().showMessage("请至少选择 2 个手工 PAD 再执行对齐。")
            return
        if mode == "left":
            target = min(item.pad.x_mil - item.pad.width_mil / 2 for item in selected)
            for item in selected:
                item.pad.x_mil = target + item.pad.width_mil / 2
        elif mode == "right":
            target = max(item.pad.x_mil + item.pad.width_mil / 2 for item in selected)
            for item in selected:
                item.pad.x_mil = target - item.pad.width_mil / 2
        elif mode == "top":
            target = min(item.pad.y_mil - item.pad.height_mil / 2 for item in selected)
            for item in selected:
                item.pad.y_mil = target + item.pad.height_mil / 2
        elif mode == "bottom":
            target = max(item.pad.y_mil + item.pad.height_mil / 2 for item in selected)
            for item in selected:
                item.pad.y_mil = target - item.pad.height_mil / 2
        else:
            return
        for item in selected:
            item.sync_from_pad()
        self._sync_manual_board_pads()
        self.update_bond_items()
        self.statusBar().showMessage(f"已对齐 {len(selected)} 个手工 PAD。")

    def distribute_selected_manual_pads(self, axis: str) -> None:
        selected = self._selected_manual_pad_items()
        if len(selected) < 3:
            self.statusBar().showMessage("请至少选择 3 个手工 PAD 再执行等距分布。")
            return
        attr = "x_mil" if axis == "x" else "y_mil"
        selected.sort(key=lambda item: getattr(item.pad, attr))
        first = getattr(selected[0].pad, attr)
        last = getattr(selected[-1].pad, attr)
        spacing = (last - first) / (len(selected) - 1)
        for index, item in enumerate(selected):
            setattr(item.pad, attr, first + spacing * index)
            item.sync_from_pad()
        self._sync_manual_board_pads()
        self.update_bond_items()
        direction = "水平" if axis == "x" else "垂直"
        self.statusBar().showMessage(f"已{direction}等距分布 {len(selected)} 个手工 PAD。")

    def load_gds_file(self, path: str) -> None:
        try:
            chip = load_gds(
                path,
                self.cb_layer.value(),
                self.cb_datatype.value(),
                self.ap_layer.value(),
                self.ap_texttype.value(),
                self.search_depth.value(),
            )
        except Exception as exc:
            self._show_error("GDS 读取或 PAD 识别失败", exc)
            return
        if self.chip_item:
            self.scene.removeItem(self.chip_item)
        self.chip = chip
        self.project.gds_path = chip.path
        self.project.cb_layer = chip.cb_layer
        self.project.cb_datatype = chip.cb_datatype
        self.project.ap_layer = chip.ap_layer
        self.project.ap_texttype = chip.ap_texttype
        self.project.search_depth = chip.search_depth
        self.chip_item = ChipItem(chip, self.chip_transform_changed)
        self.scene.addItem(self.chip_item)
        self.chip_item.set_interactive(not self.view.wire_mode)
        self.apply_transform_controls()
        self.gds_label.setText(Path(chip.path).name)
        self.gds_info.setText(
            f"{chip.cell_name}，深度 {chip.search_depth} 识别 {len(chip.pads)} 个命名 CB Drawing PAD"
        )
        self.clear_bonds()
        self.fit_scene()

    def reload_gds(self) -> None:
        if self.project.gds_path:
            self.load_gds_file(self.project.gds_path)

    def apply_transform_controls(self) -> None:
        if not self.chip_item:
            return
        x_value = self.chip_x.value()
        y_value = self.chip_y.value()
        rotation_value = self.chip_rotation.value()
        self.updating_transform = True
        self.chip_item.setPos(x_value, -y_value)
        self.chip_item.setRotation(rotation_value)
        self.updating_transform = False
        self.project.chip_x_mil = x_value
        self.project.chip_y_mil = y_value
        self.project.chip_rotation_deg = rotation_value
        self.update_bond_items()

    def chip_transform_changed(self) -> None:
        if not self.chip_item or self.updating_transform:
            return
        for box, value in (
            (self.chip_x, self.chip_item.pos().x()),
            (self.chip_y, -self.chip_item.pos().y()),
            (self.chip_rotation, self.chip_item.rotation()),
        ):
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)
        self.project.chip_x_mil = self.chip_item.pos().x()
        self.project.chip_y_mil = -self.chip_item.pos().y()
        self.project.chip_rotation_deg = self.chip_item.rotation()
        self.update_bond_items()

    def _endpoint_at(self, scene_pos: QPointF, include_nearest: bool = True) -> tuple[str, str] | None:
        for item in self.scene.items(scene_pos):
            current = item
            while current is not None:
                if isinstance(current, (ChipPadHitItem, ChipPadLabelItem)):
                    return ("chip", current.pad_name)
                if isinstance(current, BoardPadItem):
                    return ("board", current.pad.number)
                current = current.parentItem()

        if not include_nearest:
            return None
        tolerance = self.view.scene_tolerance(22)
        chip_name = self.chip_item.nearest_pad(scene_pos, tolerance) if self.chip_item else None
        board_name = self._nearest_board_pad(scene_pos, tolerance)
        if chip_name:
            return ("chip", chip_name)
        if board_name:
            return ("board", board_name)
        return None

    def _set_pending_endpoint(
        self,
        endpoint: tuple[str, str] | None,
        free_pos: QPointF | None = None,
    ) -> None:
        for item in self.board_items.values():
            item.set_pending(False)
        if self.chip_item:
            self.chip_item.set_pending_pad(None)
        if self.pending_free_item:
            self.scene.removeItem(self.pending_free_item)
            self.pending_free_item = None
        self.pending_free_pos = None
        self.pending_endpoint = endpoint
        if endpoint is None:
            return
        side, name = endpoint
        if side == "chip" and self.chip_item:
            self.chip_item.set_pending_pad(name)
        elif side == "board" and name in self.board_items:
            self.board_items[name].set_pending(True)
        elif side == "free" and free_pos is not None:
            self.pending_free_pos = QPointF(free_pos)
            self.pending_free_item = FreeEndpointMarkerItem(free_pos)
            self.scene.addItem(self.pending_free_item)

    def handle_canvas_click(self, scene_pos: QPointF) -> None:
        if not self.chip_item or not self.board_items:
            self.statusBar().showMessage("请先加载 PcbLib 和 GDS。")
            return
        endpoint = self._endpoint_at(scene_pos, include_nearest=False)
        if endpoint is None:
            bond_item = self._bond_at(scene_pos)
            if bond_item:
                self.scene.clearSelection()
                bond_item.setSelected(True)
                self._set_pending_endpoint(None)
                self.statusBar().showMessage(
                    f"已选择 BondWire {bond_item.index}：{bond_item.chip_pad} -> PCB PAD {bond_item.board_pad}；"
                    "点击“删除打线”、删除所选或按 Delete 删除。"
                )
                return
            endpoint = self._endpoint_at(scene_pos)
        if endpoint is None:
            self.statusBar().showMessage("未点中 PAD；也可以直接点击芯片外侧标签。")
            return
        if self.pending_endpoint is None:
            self._set_pending_endpoint(endpoint)
            side = "芯片" if endpoint[0] == "chip" else "PCB"
            self.statusBar().showMessage(f"已选择{side} PAD {endpoint[1]}，请选择另一端。")
            return
        if self.pending_endpoint[0] == endpoint[0] and endpoint[0] != "free":
            self._set_pending_endpoint(endpoint)
            self.statusBar().showMessage("已更新同侧起点，请选择另一侧 PAD。")
            return
        pending_endpoint = self.pending_endpoint
        pending_free_pos = QPointF(self.pending_free_pos) if self.pending_free_pos is not None else None
        self._set_pending_endpoint(None)
        self.add_connection(pending_endpoint, pending_free_pos, endpoint, None)

    def handle_canvas_double_click(self, scene_pos: QPointF) -> None:
        if not self.view.wire_mode:
            return
        if not self.chip_item or not self.board_items:
            self.statusBar().showMessage("请先加载 PcbLib 和 GDS。")
            return
        if self._endpoint_at(scene_pos, include_nearest=False) is not None or self._bond_at(scene_pos):
            self.statusBar().showMessage("双击自由端点需要位于非 PAD、非连线区域。")
            return
        free_endpoint = ("free", "FREE")
        if self.pending_endpoint is None:
            self._set_pending_endpoint(free_endpoint, scene_pos)
            self.statusBar().showMessage("已创建自由连接端点，请点击 PAD 或双击另一个非 PAD 区域。")
            return
        pending_endpoint = self.pending_endpoint
        pending_free_pos = QPointF(self.pending_free_pos) if self.pending_free_pos is not None else None
        self._set_pending_endpoint(None)
        self.add_connection(pending_endpoint, pending_free_pos, free_endpoint, scene_pos)

    def _bond_at(self, scene_pos: QPointF) -> BondWireItem | None:
        for item in self.scene.items(scene_pos):
            current = item
            while current is not None:
                if isinstance(current, BondWireItem):
                    return current
                current = current.parentItem()
        return None

    def _nearest_board_pad(self, scene_pos: QPointF, max_distance: float) -> str | None:
        best_name = None
        best_distance = max_distance
        for name, item in self.board_items.items():
            if item.shape().contains(item.mapFromScene(scene_pos)):
                return name
            distance = math.hypot(item.scenePos().x() - scene_pos.x(), item.scenePos().y() - scene_pos.y())
            if distance < best_distance:
                best_name = name
                best_distance = distance
        return best_name

    def add_bond(self, chip_pad: str, board_pad: str) -> None:
        self._append_bond(Bond(chip_pad=chip_pad, board_pad=board_pad))

    def add_connection(
        self,
        first: tuple[str, str],
        first_free_pos: QPointF | None,
        second: tuple[str, str],
        second_free_pos: QPointF | None,
    ) -> None:
        endpoints = [(first, first_free_pos), (second, second_free_pos)]
        chip = next(((endpoint, pos) for endpoint, pos in endpoints if endpoint[0] == "chip"), None)
        board = next(((endpoint, pos) for endpoint, pos in endpoints if endpoint[0] == "board"), None)
        free = [(endpoint, pos) for endpoint, pos in endpoints if endpoint[0] == "free"]

        if chip and board:
            bond = Bond(chip_pad=chip[0][1], board_pad=board[0][1])
        elif chip and free and free[0][1] is not None:
            pos = free[0][1]
            bond = Bond(
                chip_pad=chip[0][1],
                board_endpoint_type="free",
                board_free_x_mil=pos.x(),
                board_free_y_mil=pos.y(),
                board_free_z_mil=self.project.pcb_surface_z_mil,
            )
        elif board and free and free[0][1] is not None:
            pos = free[0][1]
            bond = Bond(
                board_pad=board[0][1],
                chip_endpoint_type="free",
                chip_free_x_mil=pos.x(),
                chip_free_y_mil=pos.y(),
                chip_free_z_mil=self.project.chip_surface_z_mil,
            )
        elif len(free) == 2 and all(pos is not None for _, pos in free):
            first_pos, second_pos = free[0][1], free[1][1]
            bond = Bond(
                chip_endpoint_type="free",
                board_endpoint_type="free",
                chip_free_x_mil=first_pos.x(),
                chip_free_y_mil=first_pos.y(),
                chip_free_z_mil=self.project.chip_surface_z_mil,
                board_free_x_mil=second_pos.x(),
                board_free_y_mil=second_pos.y(),
                board_free_z_mil=self.project.pcb_surface_z_mil,
            )
        else:
            self.statusBar().showMessage("不支持连接两个同类型 PAD，请选择另一侧 PAD 或自由端点。")
            return
        self._append_bond(bond)

    def _append_bond(self, bond: Bond) -> None:
        if bond in self.project.bonds:
            self.statusBar().showMessage("该 BondWire 已存在。")
            return
        self.project.bonds.append(bond)
        self.rebuild_bonds()
        self.statusBar().showMessage(
            f"已建立 {self._bond_endpoint_label(bond, 'chip')} -> {self._bond_endpoint_label(bond, 'board')}"
        )

    @staticmethod
    def _bond_endpoint_label(bond: Bond, endpoint: str) -> str:
        endpoint_type = getattr(bond, f"{endpoint}_endpoint_type")
        if endpoint_type == "free":
            x = getattr(bond, f"{endpoint}_free_x_mil")
            y = getattr(bond, f"{endpoint}_free_y_mil")
            return f"FREE ({x:.2f}, {y:.2f})"
        return getattr(bond, f"{endpoint}_pad")

    def _bond_is_valid(self, bond: Bond) -> bool:
        chip_valid = bond.chip_endpoint_type == "free" or (
            self.chip_item is not None and bond.chip_pad in self.chip_item.pad_local
        )
        board_valid = bond.board_endpoint_type == "free" or bond.board_pad in self.board_items
        return chip_valid and board_valid

    def rebuild_bonds(self) -> None:
        for item in self.bond_items:
            self.scene.removeItem(item)
        self.bond_items.clear()
        valid: list[Bond] = []
        if self.chip_item:
            for index, bond in enumerate(self.project.bonds, 1):
                if not self._bond_is_valid(bond):
                    continue
                item = BondWireItem(
                    index,
                    self._bond_endpoint_label(bond, "chip"),
                    self._bond_endpoint_label(bond, "board"),
                    self.project.bondwire_color,
                    self.project.bondwire_width_mil,
                    lambda endpoint, scene_pos, current_bond=bond: self.bond_endpoint_moved(
                        current_bond,
                        endpoint,
                        scene_pos,
                    ),
                )
                self.scene.addItem(item)
                self.bond_items.append(item)
                valid.append(bond)
        self.project.bonds = valid
        self.update_bond_items()
        self.refresh_table()
        self._refresh_3d_dialog()

    def update_bond_items(self, refresh_3d: bool = True) -> None:
        if not self.chip_item:
            return
        for bond, item in zip(self.project.bonds, self.bond_items):
            item.update_curve([QPointF(x, y) for x, y, _z in self._bond_points_3d(bond)])
        self.refresh_table()
        if refresh_3d:
            self._refresh_3d_dialog()

    def _bond_endpoints(self, bond: Bond) -> tuple[QPointF, QPointF]:
        if bond.chip_endpoint_type == "free":
            chip_point = QPointF(bond.chip_free_x_mil, bond.chip_free_y_mil)
        else:
            chip_local = self.chip_item.pad_local[bond.chip_pad] + QPointF(
                bond.chip_offset_x_mil,
                bond.chip_offset_y_mil,
            )
            chip_point = self.chip_item.mapToScene(chip_local)
        if bond.board_endpoint_type == "free":
            board_point = QPointF(bond.board_free_x_mil, bond.board_free_y_mil)
        else:
            board_point = self.board_items[bond.board_pad].mapToScene(
                QPointF(bond.board_offset_x_mil, bond.board_offset_y_mil)
            )
        return (
            chip_point,
            board_point,
        )

    def _bond_endpoints_3d(
        self, bond: Bond
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        chip_point, board_point = self._bond_endpoints(bond)
        chip_z = (
            bond.chip_free_z_mil
            if bond.chip_endpoint_type == "free"
            else self.project.chip_surface_z_mil
        )
        board_z = (
            bond.board_free_z_mil
            if bond.board_endpoint_type == "free"
            else self.project.pcb_surface_z_mil
        )
        return (
            (chip_point.x(), chip_point.y(), chip_z),
            (board_point.x(), board_point.y(), board_z),
        )

    def _bond_middle_point_3d(self, bond: Bond) -> tuple[float, float, float]:
        start, end = self._bond_endpoints_3d(bond)
        return bond_midpoint(bond, start, end)

    def _set_bond_middle_point_3d(
        self, bond: Bond, middle: tuple[float, float, float]
    ) -> None:
        start, end = self._bond_endpoints_3d(bond)
        control = midpoint_to_control(start, middle, end)
        bond.control_x_mil, bond.control_y_mil, bond.control_z_mil = control

    def _bond_points_3d(self, bond: Bond) -> list[tuple[float, float, float]]:
        start, end = self._bond_endpoints_3d(bond)
        return sample_quadratic(start, bond_control_point(bond, start, end), end)

    def _bond_length_3d(self, bond: Bond) -> float:
        start, end = self._bond_endpoints_3d(bond)
        return quadratic_length(start, bond_control_point(bond, start, end), end)

    def _bond_length_for_middle(
        self, bond: Bond, middle: tuple[float, float, float]
    ) -> float:
        start, end = self._bond_endpoints_3d(bond)
        return quadratic_length(start, midpoint_to_control(start, middle, end), end)

    def bond_endpoint_moved(self, bond: Bond, endpoint: str, scene_pos: QPointF) -> None:
        if not self.chip_item:
            return
        if endpoint == "chip":
            if bond.chip_endpoint_type == "free":
                bond.chip_free_x_mil = scene_pos.x()
                bond.chip_free_y_mil = scene_pos.y()
            else:
                local = self.chip_item.mapFromScene(scene_pos) - self.chip_item.pad_local[bond.chip_pad]
                bond.chip_offset_x_mil = local.x()
                bond.chip_offset_y_mil = local.y()
        else:
            if bond.board_endpoint_type == "free":
                bond.board_free_x_mil = scene_pos.x()
                bond.board_free_y_mil = scene_pos.y()
            else:
                local = self.board_items[bond.board_pad].mapFromScene(scene_pos)
                bond.board_offset_x_mil = local.x()
                bond.board_offset_y_mil = local.y()
        self.update_bond_items()

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.project.bonds))
        if not self.chip_item:
            return
        for row, bond in enumerate(self.project.bonds):
            length = self._bond_length_3d(bond)
            for column, value in enumerate(
                (
                    row + 1,
                    self._bond_endpoint_label(bond, "chip"),
                    self._bond_endpoint_label(bond, "board"),
                    f"{length:.3f}",
                )
            ):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, column, item)

    def _refresh_3d_dialog(self) -> None:
        if self.three_d_dialog is not None and self.three_d_dialog.isVisible():
            self.three_d_dialog.refresh_scene()

    def _sync_3d_selection_from_table(self) -> None:
        if self.three_d_dialog is None or not self.three_d_dialog.isVisible():
            return
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if rows:
            self.three_d_dialog.select_bond(rows[0], sync_table=False)

    def show_3d_view(self) -> None:
        if not self.project.bonds:
            self.statusBar().showMessage("请先创建至少一条 BondWire。")
            return
        if self.three_d_dialog is None:
            self.three_d_dialog = Bond3DDialog(self)
            self.three_d_dialog.finished.connect(lambda _result: setattr(self, "three_d_dialog", None))
        self.three_d_dialog.refresh_scene()
        self.three_d_dialog.show()
        self.three_d_dialog.raise_()
        self.three_d_dialog.activateWindow()

    def delete_selected_bonds(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        rows.update(index.row() for index in self.table.selectedIndexes())
        for item in self.scene.selectedItems():
            current = item
            while current is not None:
                if isinstance(current, BondWireItem):
                    rows.add(current.index - 1)
                    break
                current = current.parentItem()
        if not rows:
            self.statusBar().showMessage("请先在画布中点击 BondWire，或在打线关系表中选择需要删除的行。")
            return
        self.project.bonds = [bond for index, bond in enumerate(self.project.bonds) if index not in rows]
        self.rebuild_bonds()
        self.statusBar().showMessage(f"已删除 {len(rows)} 条 BondWire。")

    def clear_bonds(self) -> None:
        self._set_pending_endpoint(None)
        self.project.bonds.clear()
        self.rebuild_bonds()

    def fit_scene(self) -> None:
        bounds = self.scene.itemsBoundingRect()
        if bounds.isValid() and not bounds.isEmpty():
            margin = max(bounds.width(), bounds.height()) * 0.08 + 2
            bounds = bounds.adjusted(-margin, -margin, margin, margin)
            self.scene.setSceneRect(bounds)
            self.view.fitInView(bounds, Qt.KeepAspectRatio)

    def choose_save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存工程", self.project_path, "BondWire Project (*.bondwire.json)")
        if path:
            self.save_project(path)

    def save_project(self, path: str) -> None:
        if not path.lower().endswith(".json"):
            path += ".bondwire.json"
        Path(path).write_text(
            json.dumps(self.project.make_paths_relative(path), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.project_path = path
        self.statusBar().showMessage(f"工程已保存：{path}")

    def choose_open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开工程", "", "BondWire Project (*.json)")
        if path:
            self.open_project(path)

    def open_project(self, path: str) -> None:
        try:
            data = ProjectData.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
            data.resolve_paths(path)
            transform_values = (data.chip_x_mil, data.chip_y_mil, data.chip_rotation_deg)
            pcb_rotation = data.pcb_rotation_deg
            self.cb_layer.setValue(data.cb_layer)
            self.cb_datatype.setValue(data.cb_datatype)
            self.ap_layer.setValue(data.ap_layer)
            self.ap_texttype.setValue(data.ap_texttype)
            self.search_depth.setValue(data.search_depth)
            if data.pcb_path:
                self.load_pcblib_file(data.pcb_path)
            if data.gds_path:
                self.load_gds_file(data.gds_path)
            self.project = data
            if not data.pcb_path:
                if self.board_assembly_item:
                    self.scene.removeItem(self.board_assembly_item)
                self.board = None
                self.board_preview_item = None
                self.board_assembly_item = None
                self.board_items.clear()
                self._ensure_board_container()
            self._render_manual_board_pads()
            self._update_pcb_info()
            self.wire_width.blockSignals(True)
            self.wire_width.setValue(data.bondwire_width_mil)
            self.wire_width.blockSignals(False)
            self.pdf_include_labels.blockSignals(True)
            self.pdf_include_labels.setChecked(data.pdf_include_chip_pad_labels)
            self.pdf_include_labels.blockSignals(False)
            self._update_wire_color_button()
            for box, value in zip((self.chip_x, self.chip_y, self.chip_rotation), transform_values):
                box.blockSignals(True)
                box.setValue(value)
                box.blockSignals(False)
            self.apply_transform_controls()
            self.pcb_rotation.blockSignals(True)
            self.pcb_rotation.setValue(pcb_rotation)
            self.pcb_rotation.blockSignals(False)
            self.apply_pcb_transform()
            self.rebuild_bonds()
            self.project_path = path
        except Exception as exc:
            self._show_error("工程打开失败", exc)

    def choose_export_pdf(self) -> None:
        default = str(Path(self.project_path).with_suffix(".pdf")) if self.project_path else "bondwire_drawing.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "导出打线 PDF", default, "PDF (*.pdf)")
        if path:
            self.export_pdf(path)

    def choose_export_ad26_script(self) -> None:
        default = str(Path(self.project_path).with_suffix(".pas")) if self.project_path else "ad26_footprint_reference.pas"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 AD26 封装参考脚本",
            default,
            "Altium DelphiScript (*.pas);;Text (*.txt)",
        )
        if path:
            self.export_ad26_script(path)

    def export_ad26_script(self, path: str) -> None:
        if not self.board_items:
            raise ValueError("导出 AD26 参考封装前请先导入或绘制 PCB PAD。")
        pads = sorted(
            (item.pad for item in self.board_items.values()),
            key=lambda pad: (0, int(pad.number)) if pad.number.isdigit() else (1, pad.number),
        )
        footprint_name = self.board.footprint_name if self.board else "GDS_BONDWIRE_REF"
        lines = [
            "{ Generated by GDS BondWire Planner. }",
            "{ Run this script from an Altium Designer 26 PCB Library document as a pad-placement reference. }",
            "{ Coordinates and sizes are in mil; layer is TopLayer by default. }",
            "",
            "Procedure Create_GDS_BondWire_Reference_Footprint;",
            "Var",
            "    Board     : IPCB_Board;",
            "    Component : IPCB_Component;",
            "    Pad       : IPCB_Pad;",
            "Begin",
            "    Board := PCBServer.GetCurrentPCBBoard;",
            "    If Board = Nil Then Exit;",
            "    PCBServer.PreProcess;",
            "    Component := PCBServer.PCBObjectFactory(eComponentObject, eNoDimension, eCreate_Default);",
            f"    Component.Name.Text := '{footprint_name}_BONDWIRE_REF';",
            "    Board.AddPCBObject(Component);",
            "",
        ]
        for pad in pads:
            shape = {
                "round": "eRounded",
                "roundrect": "eRoundedRectangle",
                "rect": "eRectangular",
                "octagon": "eOctagonal",
            }.get(pad.shape, "eRoundedRectangle")
            lines.extend(
                [
                    f"    {{ PAD {pad.number} }}",
                    "    Pad := PCBServer.PCBObjectFactory(ePadObject, eNoDimension, eCreate_Default);",
                    f"    Pad.Name := '{pad.number}';",
                    f"    Pad.X := MilsToCoord({pad.x_mil:.6f});",
                    f"    Pad.Y := MilsToCoord({-pad.y_mil:.6f});",
                    f"    Pad.TopXSize := MilsToCoord({pad.width_mil:.6f});",
                    f"    Pad.TopYSize := MilsToCoord({pad.height_mil:.6f});",
                    f"    Pad.Rotation := {pad.rotation_deg:.6f};",
                    f"    Pad.TopShape := {shape};",
                    "    Pad.Layer := eTopLayer;",
                    "    Component.AddPCBObject(Pad);",
                    "",
                ]
            )
        lines.extend(
            [
                "    Board.ViewManager_FullUpdate;",
                "    PCBServer.PostProcess;",
                "End;",
                "",
                "Begin",
                "    Create_GDS_BondWire_Reference_Footprint;",
                "End.",
                "",
                "{ PAD_TABLE_CSV",
                "number,x_mil,y_mil,width_mil,height_mil,rotation_deg,shape,manual",
            ]
        )
        for pad in pads:
            lines.append(
                f"{pad.number},{pad.x_mil:.6f},{pad.y_mil:.6f},{pad.width_mil:.6f},"
                f"{pad.height_mil:.6f},{pad.rotation_deg:.6f},{pad.shape},{int(pad.manual)}"
            )
        lines.append("}")
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        self.statusBar().showMessage(f"AD26 封装参考脚本已导出：{path}")

    def export_pdf(self, path: str) -> None:
        if not self.board or not self.chip:
            raise ValueError("导出 PDF 前需要加载 PcbLib 和 GDS。")
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageSize(QPrinter.A3)
        printer.setOrientation(QPrinter.Landscape)
        printer.setFullPage(True)

        painter = QPainter(printer)
        page = QRectF(printer.pageRect(QPrinter.DevicePixel))
        margin = page.width() * 0.025
        title_height = page.height() * 0.07
        drawing_rect = QRectF(margin, margin + title_height, page.width() * 0.69, page.height() - 2 * margin - title_height)
        table_rect = QRectF(drawing_rect.right() + margin, drawing_rect.top(), page.right() - drawing_rect.right() - 2 * margin, drawing_rect.height())

        title_font = QFont("Arial", 18, QFont.Bold)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(margin, margin, page.width() - 2 * margin, title_height),
            Qt.AlignLeft | Qt.AlignVCenter,
            "BOND WIRE DRAWING",
        )
        show_labels = self.pdf_include_labels.isChecked()
        self.project.pdf_include_chip_pad_labels = show_labels
        if self.chip_item and not show_labels:
            self.chip_item.set_pad_labels_visible(False)
        try:
            source = self.scene.itemsBoundingRect().adjusted(-2, -2, 2, 2)
            self.scene.render(painter, drawing_rect, source, Qt.KeepAspectRatio)
            self._paint_pdf_table(painter, table_rect)
        finally:
            if self.chip_item and not show_labels:
                self.chip_item.set_pad_labels_visible(True)
            painter.end()
        self.statusBar().showMessage(f"PDF 已导出：{path}")

    def _paint_pdf_table(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setPen(QPen(Qt.black, 2))
        font = QFont("Arial", 8)
        painter.setFont(font)
        lines = [
            f"PCB: {Path(self.board.path).name if self.board else '-'}",
            f"GDS: {Path(self.chip.path).name if self.chip else '-'}",
            f"Cell: {self.chip.cell_name if self.chip else '-'}",
            f"CB Drawing: {self.cb_layer.value()}/{self.cb_datatype.value()}    AP Pin: {self.ap_layer.value()}/{self.ap_texttype.value()}",
            f"PAD search depth: {self.search_depth.value()}",
            f"Chip X/Y/Rot: {self.chip_x.value():.4f} / {self.chip_y.value():.4f} mil / {self.chip_rotation.value():.2f} deg",
            f"PCB rotation: {self.project.pcb_rotation_deg:.2f} deg",
            f"BondWire: {self.project.bondwire_color} / {self.project.bondwire_width_mil:.3f} mil",
        ]
        line_height = rect.height() * 0.032
        y = rect.top()
        for line in lines:
            painter.drawText(QRectF(rect.left(), y, rect.width(), line_height), Qt.AlignLeft | Qt.AlignVCenter, line)
            y += line_height
        y += line_height * 0.5

        row_height = min(rect.height() * 0.035, (rect.bottom() - y) / max(len(self.project.bonds) + 1, 1))
        widths = [0.10, 0.43, 0.25, 0.22]
        headers = ["#", "ENDPOINT A", "ENDPOINT B", "LENGTH/mil"]
        rows = []
        if self.chip_item:
            for index, bond in enumerate(self.project.bonds, 1):
                length = self._bond_length_3d(bond)
                rows.append(
                    [
                        str(index),
                        self._bond_endpoint_label(bond, "chip"),
                        self._bond_endpoint_label(bond, "board"),
                        f"{length:.3f}",
                    ]
                )
        for row_index, values in enumerate([headers] + rows):
            x = rect.left()
            if row_index == 0:
                painter.fillRect(QRectF(rect.left(), y, rect.width(), row_height), QColor("#d9e2ec"))
            for value, width in zip(values, widths):
                cell = QRectF(x, y, rect.width() * width, row_height)
                painter.drawRect(cell)
                painter.drawText(cell.adjusted(5, 0, -5, 0), Qt.AlignLeft | Qt.AlignVCenter, value)
                x += rect.width() * width
            y += row_height
        painter.restore()

    def _show_error(self, title: str, error: Exception) -> None:
        QMessageBox.critical(self, title, str(error))
        self.statusBar().showMessage(f"{title}: {error}")
