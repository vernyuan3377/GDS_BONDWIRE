from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import (
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Bond3DView(QWidget):
    def __init__(self, dialog: "Bond3DDialog") -> None:
        super().__init__(dialog)
        self.dialog = dialog
        self.azimuth = math.radians(-28.0)
        self.elevation = math.radians(34.0)
        self.zoom = 1.0
        self._last_pos = None
        self._mode = ""
        self._project_offset = QPointF()
        self._project_scale = 1.0
        self._board_metal_key = None
        self._board_metal_pixmap = QPixmap()
        self.setMinimumSize(720, 520)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

    def _raw_project(self, point: tuple[float, float, float]) -> QPointF:
        x, y, z = point
        ca, sa = math.cos(self.azimuth), math.sin(self.azimuth)
        ce, se = math.cos(self.elevation), math.sin(self.elevation)
        xr = x * ca - y * sa
        yr = x * sa + y * ca
        return QPointF(xr, -(yr * ce + z * se))

    def _project(self, point: tuple[float, float, float]) -> QPointF:
        raw = self._raw_project(point)
        return QPointF(
            raw.x() * self._project_scale + self._project_offset.x(),
            raw.y() * self._project_scale + self._project_offset.y(),
        )

    def _scene_points(self) -> list[tuple[float, float, float]]:
        points: list[tuple[float, float, float]] = []
        main = self.dialog.main_window
        for bond in main.project.bonds:
            points.extend(main._bond_points_3d(bond))
            points.append(main._bond_middle_point_3d(bond))
        points.extend(self._plane_corners())
        return points

    def _plane_corners(self) -> list[tuple[float, float, float]]:
        main = self.dialog.main_window
        result: list[tuple[float, float, float]] = []
        if main.board_preview_item is not None:
            rect = main.board_preview_item.boundingRect()
            z = main.project.pcb_surface_z_mil
            result.extend(
                [
                    (*self._scene_xy(main.board_preview_item, QPointF(rect.left(), rect.top())), z),
                    (*self._scene_xy(main.board_preview_item, QPointF(rect.right(), rect.top())), z),
                    (*self._scene_xy(main.board_preview_item, QPointF(rect.right(), rect.bottom())), z),
                    (*self._scene_xy(main.board_preview_item, QPointF(rect.left(), rect.bottom())), z),
                ]
            )
        if main.chip_item is not None:
            rect = main.chip_item._chip_rect()
            z = main.project.chip_surface_z_mil
            result.extend(
                [
                    (*self._scene_xy(main.chip_item, QPointF(rect.left(), rect.top())), z),
                    (*self._scene_xy(main.chip_item, QPointF(rect.right(), rect.top())), z),
                    (*self._scene_xy(main.chip_item, QPointF(rect.right(), rect.bottom())), z),
                    (*self._scene_xy(main.chip_item, QPointF(rect.left(), rect.bottom())), z),
                ]
            )
        return result

    @staticmethod
    def _scene_xy(item, point: QPointF) -> tuple[float, float]:
        scene = item.mapToScene(point)
        return scene.x(), scene.y()

    def _draw_chip_pads(self, painter: QPainter) -> None:
        main = self.dialog.main_window
        if main.chip_item is not None:
            for path in main.chip_item.pad_paths.values():
                for polygon in path.toSubpathPolygons():
                    points = [
                        self._project(
                            (
                                *self._scene_xy(main.chip_item, point),
                                main.project.chip_surface_z_mil + 0.02,
                            )
                        )
                        for point in polygon
                    ]
                    if len(points) >= 3:
                        self._draw_polygon(painter, points, QColor(176, 127, 25, 235), QColor("#ffe276"))

    def _load_board_metal_pixmap(self) -> QPixmap:
        board = self.dialog.main_window.board
        key = (board.path, board.first_metal_layer) if board is not None else None
        if key == self._board_metal_key:
            return self._board_metal_pixmap
        self._board_metal_key = key
        self._board_metal_pixmap = QPixmap()
        if board is None or not board.first_metal_svg:
            return self._board_metal_pixmap
        renderer = QSvgRenderer(board.first_metal_svg)
        default_size = renderer.defaultSize()
        longest = max(default_size.width(), default_size.height(), 1)
        scale = 1800 / longest
        image = QImage(
            max(1, round(default_size.width() * scale)),
            max(1, round(default_size.height() * scale)),
            QImage.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.transparent)
        image_painter = QPainter(image)
        renderer.render(image_painter)
        image_painter.end()
        self._board_metal_pixmap = QPixmap.fromImage(image)
        return self._board_metal_pixmap

    def _draw_board_metal(self, painter: QPainter) -> None:
        main = self.dialog.main_window
        board = main.board
        pixmap = self._load_board_metal_pixmap()
        if board is None or board.first_metal_bbox_mil is None or pixmap.isNull():
            return
        (min_x, min_y), (max_x, max_y) = board.first_metal_bbox_mil
        z = main.project.pcb_surface_z_mil + 0.02
        top_left = main.board_scene_point(min_x, min_y)
        top_right = main.board_scene_point(max_x, min_y)
        bottom_right = main.board_scene_point(max_x, max_y)
        bottom_left = main.board_scene_point(min_x, max_y)
        target = QPolygonF(
            [
                self._project((top_left.x(), top_left.y(), z)),
                self._project((top_right.x(), top_right.y(), z)),
                self._project((bottom_right.x(), bottom_right.y(), z)),
                self._project((bottom_left.x(), bottom_left.y(), z)),
            ]
        )
        source = QPolygonF(
            [
                QPointF(0, 0),
                QPointF(pixmap.width(), 0),
                QPointF(pixmap.width(), pixmap.height()),
                QPointF(0, pixmap.height()),
            ]
        )
        transform = QTransform()
        if not QTransform.quadToQuad(source, target, transform):
            return
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setTransform(transform)
        painter.drawPixmap(0, 0, pixmap)
        painter.restore()

    def _update_projection(self) -> None:
        points = self._scene_points()
        if not points:
            self._project_scale = 1.0
            self._project_offset = QPointF(self.width() / 2, self.height() / 2)
            return
        raw = [self._raw_project(point) for point in points]
        min_x = min(point.x() for point in raw)
        max_x = max(point.x() for point in raw)
        min_y = min(point.y() for point in raw)
        max_y = max(point.y() for point in raw)
        available_w = max(100.0, self.width() - 70.0)
        available_h = max(100.0, self.height() - 70.0)
        self._project_scale = (
            min(available_w / max(max_x - min_x, 1.0), available_h / max(max_y - min_y, 1.0))
            * self.zoom
        )
        self._project_offset = QPointF(
            self.width() / 2 - (min_x + max_x) * self._project_scale / 2,
            self.height() / 2 - (min_y + max_y) * self._project_scale / 2,
        )

    @staticmethod
    def _draw_polygon(
        painter: QPainter,
        points: list[QPointF],
        fill: QColor,
        outline: QColor,
    ) -> None:
        path = QPainterPath()
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        path.closeSubpath()
        painter.fillPath(path, fill)
        painter.setPen(QPen(outline, 1.2))
        painter.drawPath(path)

    def paintEvent(self, _event) -> None:
        self._update_projection()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#141820"))

        corners = self._plane_corners()
        if len(corners) >= 4:
            self._draw_polygon(
                painter,
                [self._project(point) for point in corners[:4]],
                QColor(38, 72, 95, 150),
                QColor("#5d9fc4"),
            )
            self._draw_board_metal(painter)
        if len(corners) >= 8:
            self._draw_polygon(
                painter,
                [self._project(point) for point in corners[4:8]],
                QColor(90, 70, 35, 210),
                QColor("#e7bd4a"),
            )
        self._draw_chip_pads(painter)

        main = self.dialog.main_window
        for index, bond in enumerate(main.project.bonds):
            points = [self._project(point) for point in main._bond_points_3d(bond)]
            selected = index == self.dialog.selected_index
            color = QColor("#fff08a") if selected else QColor(main.project.bondwire_color)
            physical_width = bond.wire_diameter_um / 25.4 * self._project_scale
            width = max(1.3, min(12.0, physical_width)) + (1.6 if selected else 0.0)
            painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.drawPath(path)

        bond = self.dialog.selected_bond()
        if bond is not None:
            control = self._project(main._bond_middle_point_3d(bond))
            painter.setPen(QPen(QColor("#111111"), 1.2))
            painter.setBrush(QColor("#60d8ff"))
            painter.drawEllipse(control, 7.0, 7.0)

        painter.setPen(QColor("#d7dde8"))
        painter.drawText(
            14,
            22,
            "左键拖动中间点: XY    Shift+左键拖动: Z高度    右键拖动: 旋转    滚轮: 缩放",
        )
        if main.board is not None and main.board.first_metal_layer:
            painter.drawText(14, 42, f"PCB 第一金属层: {main.board.first_metal_layer}")
        painter.end()

    def _distance_to_polyline(self, pos: QPointF, points: list[QPointF]) -> float:
        best = float("inf")
        for first, second in zip(points, points[1:]):
            dx, dy = second.x() - first.x(), second.y() - first.y()
            length_sq = dx * dx + dy * dy
            if length_sq <= 0:
                continue
            t = max(
                0.0,
                min(1.0, ((pos.x() - first.x()) * dx + (pos.y() - first.y()) * dy) / length_sq),
            )
            nearest = QPointF(first.x() + t * dx, first.y() + t * dy)
            best = min(best, math.hypot(pos.x() - nearest.x(), pos.y() - nearest.y()))
        return best

    def mousePressEvent(self, event) -> None:
        self._last_pos = event.pos()
        if event.button() == Qt.RightButton:
            self._mode = "rotate"
            return
        if event.button() != Qt.LeftButton:
            return
        bond = self.dialog.selected_bond()
        if bond is not None:
            control = self._project(self.dialog.main_window._bond_middle_point_3d(bond))
            if math.hypot(event.pos().x() - control.x(), event.pos().y() - control.y()) <= 14:
                self._mode = "control_z" if event.modifiers() & Qt.ShiftModifier else "control_xy"
                return
        best_index = None
        best_distance = 12.0
        for index, candidate in enumerate(self.dialog.main_window.project.bonds):
            points = [self._project(point) for point in self.dialog.main_window._bond_points_3d(candidate)]
            distance = self._distance_to_polyline(event.pos(), points)
            if distance < best_distance:
                best_distance = distance
                best_index = index
        if best_index is not None:
            self.dialog.select_bond(best_index)
        self._mode = ""

    def mouseMoveEvent(self, event) -> None:
        if self._last_pos is None:
            return
        delta = event.pos() - self._last_pos
        self._last_pos = event.pos()
        if self._mode == "rotate":
            self.azimuth += delta.x() * 0.008
            self.elevation = max(math.radians(8), min(math.radians(82), self.elevation - delta.y() * 0.008))
            self.update()
            return
        bond = self.dialog.selected_bond()
        if bond is None or self._mode not in {"control_xy", "control_z"}:
            return
        control = self.dialog.main_window._bond_middle_point_3d(bond)
        scale = max(self._project_scale, 0.001)
        if self._mode == "control_z":
            dz = -delta.y() / scale / max(math.sin(self.elevation), 0.15)
            self.dialog.set_middle_point(control[0], control[1], control[2] + dz)
            return
        du = delta.x() / scale
        dv = delta.y() / scale
        ca, sa = math.cos(self.azimuth), math.sin(self.azimuth)
        ce = max(math.cos(self.elevation), 0.15)
        dyr = -dv / ce
        dx = du * ca + dyr * sa
        dy = -du * sa + dyr * ca
        self.dialog.set_middle_point(control[0] + dx, control[1] + dy, control[2])

    def mouseReleaseEvent(self, _event) -> None:
        self._last_pos = None
        self._mode = ""

    def wheelEvent(self, event) -> None:
        self.zoom = max(0.25, min(6.0, self.zoom * (1.12 if event.angleDelta().y() > 0 else 1 / 1.12)))
        self.update()


class Bond3DDialog(QDialog):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.selected_index = 0
        self._syncing = False
        self.setWindowTitle("BondWire 3D 编辑")
        self.resize(1080, 680)

        self.view = Bond3DView(self)
        self.bond_combo = QComboBox()
        self.control_x = self._spin(-1_000_000, 1_000_000, 0.1, " mil")
        self.control_y = self._spin(-1_000_000, 1_000_000, 0.1, " mil")
        self.control_z = self._spin(-1_000_000, 1_000_000, 0.1, " mil")
        self.diameter = self._spin(0.1, 10_000, 1.0, " um")
        self.pcb_z = self._spin(-1_000_000, 1_000_000, 0.1, " mil")
        self.chip_z = self._spin(-1_000_000, 1_000_000, 0.1, " mil")
        self.length = self._spin(0.001, 10_000_000, 1.0, " mil")

        form = QFormLayout()
        form.addRow("打线", self.bond_combo)
        form.addRow("中间点 X", self.control_x)
        form.addRow("中间点 Y", self.control_y)
        form.addRow("中间点 Z", self.control_z)
        form.addRow("线径", self.diameter)
        form.addRow("PCB 表面 Z", self.pcb_z)
        form.addRow("芯片表面 Z", self.chip_z)
        form.addRow("目标 / 真实长度", self.length)

        reset_button = QPushButton("重置中间点")
        side = QVBoxLayout()
        side.addLayout(form)
        side.addWidget(reset_button)
        side.addStretch(1)
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(300)

        layout = QHBoxLayout(self)
        layout.addWidget(self.view, 1)
        layout.addWidget(side_widget)

        self.bond_combo.currentIndexChanged.connect(self.select_bond)
        for control in (self.control_x, self.control_y, self.control_z):
            control.valueChanged.connect(self._control_value_changed)
        self.diameter.valueChanged.connect(self._diameter_changed)
        self.length.valueChanged.connect(self._length_changed)
        self.pcb_z.valueChanged.connect(self._surface_z_changed)
        self.chip_z.valueChanged.connect(self._surface_z_changed)
        reset_button.clicked.connect(self.reset_middle_point)
        self.refresh_scene()

    @staticmethod
    def _spin(minimum: float, maximum: float, step: float, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        return spin

    def selected_bond(self):
        if 0 <= self.selected_index < len(self.main_window.project.bonds):
            return self.main_window.project.bonds[self.selected_index]
        return None

    def refresh_scene(self) -> None:
        current = min(self.selected_index, max(0, len(self.main_window.project.bonds) - 1))
        self._syncing = True
        self.bond_combo.clear()
        for index, bond in enumerate(self.main_window.project.bonds, 1):
            self.bond_combo.addItem(
                f"{index}: {self.main_window._bond_endpoint_label(bond, 'chip')} -> "
                f"{self.main_window._bond_endpoint_label(bond, 'board')}"
            )
        self.selected_index = current
        self.bond_combo.setCurrentIndex(current)
        self.pcb_z.setValue(self.main_window.project.pcb_surface_z_mil)
        self.chip_z.setValue(self.main_window.project.chip_surface_z_mil)
        self._syncing = False
        self._sync_bond_controls()
        self.view.update()

    def select_bond(self, index: int, sync_table: bool = True) -> None:
        if index < 0:
            return
        self.selected_index = index
        if self.bond_combo.currentIndex() != index:
            self.bond_combo.setCurrentIndex(index)
        if sync_table and not self._syncing:
            self.main_window.table.selectRow(index)
        self._sync_bond_controls()
        self.view.update()

    def _sync_bond_controls(self) -> None:
        bond = self.selected_bond()
        if bond is None:
            return
        control = self.main_window._bond_middle_point_3d(bond)
        self._syncing = True
        self.control_x.setValue(control[0])
        self.control_y.setValue(control[1])
        self.control_z.setValue(control[2])
        self.diameter.setValue(bond.wire_diameter_um)
        self.length.setValue(self.main_window._bond_length_3d(bond))
        self._syncing = False

    def set_middle_point(self, x: float, y: float, z: float) -> None:
        bond = self.selected_bond()
        if bond is None:
            return
        start, end = self.main_window._bond_endpoints_3d(bond)
        self.main_window._set_bond_middle_point_3d(bond, (x, y, max(z, start[2], end[2])))
        self._sync_bond_controls()
        self.main_window.update_bond_items(refresh_3d=False)
        self.view.update()

    def _control_value_changed(self, _value: float) -> None:
        if self._syncing:
            return
        bond = self.selected_bond()
        if bond is None:
            return
        self.set_middle_point(self.control_x.value(), self.control_y.value(), self.control_z.value())

    def _diameter_changed(self, value: float) -> None:
        if self._syncing:
            return
        bond = self.selected_bond()
        if bond is None:
            return
        bond.wire_diameter_um = value
        self.view.update()

    def _length_changed(self, target_length: float) -> None:
        if self._syncing:
            return
        bond = self.selected_bond()
        if bond is None:
            return
        start, end = self.main_window._bond_endpoints_3d(bond)
        control = self.main_window._bond_middle_point_3d(bond)
        low = max(start[2], end[2])

        def length_at(z: float) -> float:
            return self.main_window._bond_length_for_middle(bond, (control[0], control[1], z))

        minimum = length_at(low)
        if target_length <= minimum:
            solved_z = low
        else:
            high = low + max(target_length, 10.0)
            while length_at(high) < target_length:
                high = low + (high - low) * 2
            for _ in range(48):
                middle = (low + high) / 2
                if length_at(middle) < target_length:
                    low = middle
                else:
                    high = middle
            solved_z = (low + high) / 2
        self.set_middle_point(control[0], control[1], solved_z)

    def _surface_z_changed(self, _value: float) -> None:
        if self._syncing:
            return
        self.main_window.project.pcb_surface_z_mil = self.pcb_z.value()
        self.main_window.project.chip_surface_z_mil = self.chip_z.value()
        self._sync_bond_controls()
        self.main_window.update_bond_items(refresh_3d=False)
        self.view.update()

    def reset_middle_point(self) -> None:
        bond = self.selected_bond()
        if bond is None:
            return
        bond.control_x_mil = None
        bond.control_y_mil = None
        bond.control_z_mil = None
        self._sync_bond_controls()
        self.main_window.update_bond_items(refresh_3d=False)
        self.view.update()
