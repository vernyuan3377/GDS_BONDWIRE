from __future__ import annotations

import math
from collections.abc import Callable

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsSimpleTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from .models import BoardPad, ChipData

UM_PER_MIL = 25.4


def _rounded_rect_path(rect: QRectF, shape: str, corner_radius_percent: float = 100.0) -> QPainterPath:
    path = QPainterPath()
    if "rect" in shape and "round" not in shape:
        path.addRect(rect)
    elif "oct" in shape:
        cut = min(rect.width(), rect.height()) * 0.22
        path.addPolygon(
            QPolygonF(
                [
                    QPointF(rect.left() + cut, rect.top()),
                    QPointF(rect.right() - cut, rect.top()),
                    QPointF(rect.right(), rect.top() + cut),
                    QPointF(rect.right(), rect.bottom() - cut),
                    QPointF(rect.right() - cut, rect.bottom()),
                    QPointF(rect.left() + cut, rect.bottom()),
                    QPointF(rect.left(), rect.bottom() - cut),
                    QPointF(rect.left(), rect.top() + cut),
                ]
            )
        )
        path.closeSubpath()
    else:
        radius = min(rect.width(), rect.height()) / 2 * corner_radius_percent / 100.0
        path.addRoundedRect(rect, radius, radius)
    return path


def _draw_fitted_text(
    painter: QPainter,
    text: str,
    rect: QRectF,
    color: QColor,
    bold: bool = True,
) -> None:
    font = QFont("Arial", 10, QFont.Bold if bold else QFont.Normal)
    path = QPainterPath()
    path.addText(0, 0, font, text)
    bounds = path.boundingRect()
    if bounds.width() <= 0 or bounds.height() <= 0:
        return
    scale = min(rect.width() * 0.82 / bounds.width(), rect.height() * 0.68 / bounds.height())
    painter.save()
    painter.translate(rect.center())
    painter.scale(scale, scale)
    painter.translate(-bounds.center())
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPath(path)
    painter.restore()


class BoardPadItem(QGraphicsObject):
    def __init__(self, pad: BoardPad, native_rendered: bool = False):
        super().__init__()
        self.pad = pad
        self.native_rendered = native_rendered
        self.pending = False
        self.hovered = False
        self.setPos(pad.x_mil, pad.y_mil)
        self.setRotation(-pad.rotation_deg)
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"PCB PAD {pad.number}")

    def _rect(self, expansion: float = 0.0) -> QRectF:
        width = self.pad.width_mil + expansion * 2
        height = self.pad.height_mil + expansion * 2
        return QRectF(-width / 2, -height / 2, width, height)

    def boundingRect(self) -> QRectF:
        return self._rect(self.pad.solder_expansion_mil).adjusted(-0.5, -0.5, 0.5, 0.5)

    def shape(self) -> QPainterPath:
        return _rounded_rect_path(
            self._rect(self.pad.solder_expansion_mil),
            self.pad.shape,
            self.pad.corner_radius_percent,
        )

    def set_pending(self, pending: bool) -> None:
        self.pending = pending
        self.update()

    def hoverEnterEvent(self, event) -> None:
        self.hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        del option, widget
        if self.native_rendered:
            if self.pending or self.hovered:
                painter.setPen(QPen(QColor("#00ffff") if self.hovered else QColor("#ffe600"), 0.35))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(
                    _rounded_rect_path(
                        self._rect(0.5),
                        self.pad.shape,
                        self.pad.corner_radius_percent,
                    )
                )
            _draw_fitted_text(painter, self.pad.number, self._rect(), QColor("#ffffff"))
            return
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#8d0096"))
        painter.drawPath(
            _rounded_rect_path(
                self._rect(self.pad.solder_expansion_mil),
                self.pad.shape,
                self.pad.corner_radius_percent,
            )
        )

        painter.setPen(QPen(QColor("#ff6060"), 0))
        painter.setBrush(QColor("#ff1010"))
        painter.drawPath(_rounded_rect_path(self._rect(), self.pad.shape, self.pad.corner_radius_percent))

        if self.pending or self.hovered:
            painter.setPen(QPen(QColor("#00ffff") if self.hovered else QColor("#ffe600"), 0.35))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(_rounded_rect_path(self._rect(0.5), self.pad.shape, self.pad.corner_radius_percent))

        _draw_fitted_text(painter, self.pad.number, self._rect(), QColor("#ffffff"))


class BoardAssemblyItem(QGraphicsObject):
    def boundingRect(self) -> QRectF:
        return self.childrenBoundingRect()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del painter, option, widget


class BoardNativePreviewItem(QGraphicsObject):
    def __init__(
        self,
        svg: bytes,
        bbox_mil: tuple[tuple[float, float], tuple[float, float]],
    ):
        super().__init__()
        renderer = QSvgRenderer(svg)
        default_size = renderer.defaultSize()
        longest = max(default_size.width(), default_size.height(), 1)
        render_scale = 2400 / longest
        image = QImage(
            max(1, round(default_size.width() * render_scale)),
            max(1, round(default_size.height() * render_scale)),
            QImage.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        self.pixmap = QPixmap.fromImage(image)
        (min_x, min_y), (max_x, max_y) = bbox_mil
        self.rect = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setZValue(4)

    def boundingRect(self) -> QRectF:
        return self.rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.drawPixmap(self.rect, self.pixmap, QRectF(self.pixmap.rect()))


class ChipPadHitItem(QGraphicsObject):
    def __init__(self, pad_name: str, parent: QGraphicsItem):
        super().__init__(parent)
        self.pad_name = pad_name
        self.pending = False
        self.hovered = False
        self.radius = 0.9
        self.setAcceptHoverEvents(True)
        self.setZValue(12)
        self.setToolTip(f"Chip PAD {pad_name}")

    def boundingRect(self) -> QRectF:
        return QRectF(-self.radius, -self.radius, self.radius * 2, self.radius * 2)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.boundingRect())
        return path

    def set_pending(self, pending: bool) -> None:
        self.pending = pending
        self.update()

    def hoverEnterEvent(self, event) -> None:
        self.hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        if not self.pending and not self.hovered:
            return
        painter.setPen(QPen(QColor("#00ffff") if self.hovered else QColor("#ffe600"), 0.25))
        painter.setBrush(QColor(0, 255, 255, 45) if self.hovered else QColor(255, 230, 0, 55))
        painter.drawEllipse(self.boundingRect())


class ChipPadLabelItem(QGraphicsObject):
    @staticmethod
    def preferred_width(pad_name: str) -> float:
        return max(7.0, len(pad_name) * 0.62 + 1.0)

    def __init__(self, pad_name: str, center: QPointF, parent: QGraphicsItem):
        super().__init__(parent)
        self.pad_name = pad_name
        self.pending = False
        self.width = self.preferred_width(pad_name)
        self.height = 1.5
        self.setPos(center)
        self.setZValue(15)
        self.setToolTip(f"Chip PAD {pad_name}")

    def boundingRect(self) -> QRectF:
        return QRectF(-self.width / 2, -self.height / 2, self.width, self.height)

    def set_pending(self, pending: bool) -> None:
        self.pending = pending
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setPen(QPen(QColor("#ffe600") if self.pending else QColor("#ffb000"), 0.12))
        painter.setBrush(QColor(0, 0, 0, 210))
        painter.drawRoundedRect(self.boundingRect(), 0.25, 0.25)
        _draw_fitted_text(
            painter,
            self.pad_name,
            self.boundingRect().adjusted(0.2, 0.12, -0.2, -0.12),
            QColor("#fff4ba"),
        )


class ChipItem(QGraphicsObject):
    def __init__(self, chip: ChipData, changed: Callable[[], None] | None = None):
        super().__init__()
        self.chip = chip
        self.changed = changed
        (x0, y0), (x1, y1) = chip.bbox_um
        self.center_um = ((x0 + x1) / 2, (y0 + y1) / 2)
        self.pad_local: dict[str, QPointF] = {}
        self.pad_paths: dict[str, QPainterPath] = {}
        self.hit_items: dict[str, ChipPadHitItem] = {}
        self.label_items: dict[str, ChipPadLabelItem] = {}
        self.label_sides: dict[str, str] = {}
        self.leader_items: list[QGraphicsPathItem] = []
        self.preview = QPixmap()
        if chip.preview_png:
            self.preview.loadFromData(chip.preview_png, "PNG")
        self._build_paths()
        self._build_pad_items()
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setTransformOriginPoint(0, 0)
        self.setZValue(20)
        self.setToolTip("拖动芯片；在打线模式下点击 PAD 或外侧标签。")

    def _local(self, x_um: float, y_um: float) -> QPointF:
        return QPointF(
            (x_um - self.center_um[0]) / UM_PER_MIL,
            -(y_um - self.center_um[1]) / UM_PER_MIL,
        )

    def _path_from_points(self, points: list[tuple[float, float]]) -> QPainterPath:
        path = QPainterPath()
        if not points:
            return path
        path.moveTo(self._local(*points[0]))
        for point in points[1:]:
            path.lineTo(self._local(*point))
        path.closeSubpath()
        return path

    def _build_paths(self) -> None:
        for pad in self.chip.pads:
            self.pad_local[pad.name] = self._local(pad.x_um, pad.y_um)
            self.pad_paths[pad.name] = self._path_from_points(pad.polygon_um)

    @staticmethod
    def _spread(values: list[tuple[str, float]], lower: float, upper: float, gap: float) -> dict[str, float]:
        if not values:
            return {}
        ordered = sorted(values, key=lambda item: item[1])
        placed: list[list[object]] = []
        for name, value in ordered:
            value = min(max(value, lower), upper)
            if placed:
                value = max(value, float(placed[-1][1]) + gap)
            placed.append([name, value])
        if float(placed[-1][1]) > upper:
            shift = float(placed[-1][1]) - upper
            for item in placed:
                item[1] = float(item[1]) - shift
        for index in range(len(placed) - 2, -1, -1):
            placed[index][1] = min(float(placed[index][1]), float(placed[index + 1][1]) - gap)
        if float(placed[0][1]) < lower:
            shift = lower - float(placed[0][1])
            for item in placed:
                item[1] = float(item[1]) + shift
        return {str(name): float(value) for name, value in placed}

    @staticmethod
    def _horizontal_label_placements(
        values: list[tuple[str, float]],
        outline: QRectF,
        y_for_row: Callable[[int], float],
    ) -> dict[str, QPointF]:
        placements: dict[str, QPointF] = {}
        row_right_edges: list[float] = []
        for name, x in sorted(values, key=lambda item: item[1]):
            width = ChipPadLabelItem.preferred_width(name)
            half_width = width / 2
            center_x = min(max(x, outline.left() + half_width), outline.right() - half_width)
            left_edge = center_x - half_width
            row = next(
                (index for index, right_edge in enumerate(row_right_edges) if left_edge >= right_edge + 0.35),
                len(row_right_edges),
            )
            right_edge = center_x + half_width
            if row == len(row_right_edges):
                row_right_edges.append(right_edge)
            else:
                row_right_edges[row] = right_edge
            placements[name] = QPointF(center_x, y_for_row(row))
        return placements

    def _build_pad_items(self) -> None:
        outline = self._chip_rect()
        sides: dict[str, list[tuple[str, float]]] = {
            "left": [],
            "right": [],
            "top": [],
            "bottom": [],
        }
        for name, point in self.pad_local.items():
            distances = {
                "left": abs(point.x() - outline.left()),
                "right": abs(point.x() - outline.right()),
                "top": abs(point.y() - outline.top()),
                "bottom": abs(point.y() - outline.bottom()),
            }
            side = min(distances, key=distances.get)
            self.label_sides[name] = side
            coordinate = point.y() if side in ("left", "right") else point.x()
            sides[side].append((name, coordinate))

        placements: dict[str, QPointF] = {}
        vertical_min, vertical_max = outline.top() + 0.8, outline.bottom() - 0.8
        for side in ("left", "right"):
            spread = self._spread(sides[side], vertical_min, vertical_max, 1.75)
            x = outline.left() - 5.2 if side == "left" else outline.right() + 5.2
            placements.update({name: QPointF(x, value) for name, value in spread.items()})
        placements.update(
            self._horizontal_label_placements(
                sides["top"],
                outline,
                lambda row: outline.top() - 2.2 - row * 1.9,
            )
        )
        placements.update(
            self._horizontal_label_placements(
                sides["bottom"],
                outline,
                lambda row: outline.bottom() + 2.2 + row * 1.9,
            )
        )

        for name, pad_point in self.pad_local.items():
            hit = ChipPadHitItem(name, self)
            hit.setPos(pad_point)
            self.hit_items[name] = hit

            label_point = placements[name]
            label = ChipPadLabelItem(name, label_point, self)
            self.label_items[name] = label

            side = self.label_sides[name]
            if side == "left":
                elbow = QPointF(outline.left() - 0.7, label_point.y())
                target = QPointF(label_point.x() + label.width / 2, label_point.y())
            elif side == "right":
                elbow = QPointF(outline.right() + 0.7, label_point.y())
                target = QPointF(label_point.x() - label.width / 2, label_point.y())
            elif side == "top":
                elbow = QPointF(label_point.x(), outline.top() - 0.7)
                target = QPointF(label_point.x(), label_point.y() + label.height / 2)
            else:
                elbow = QPointF(label_point.x(), outline.bottom() + 0.7)
                target = QPointF(label_point.x(), label_point.y() - label.height / 2)
            path = QPainterPath(pad_point)
            path.lineTo(elbow)
            path.lineTo(target)
            leader = QGraphicsPathItem(path, self)
            leader.setPen(QPen(QColor(255, 176, 0, 175), 0.1))
            leader.setZValue(4)
            self.leader_items.append(leader)

    def _chip_rect(self) -> QRectF:
        (x0, y0), (x1, y1) = self.chip.bbox_um
        width = abs(x1 - x0) / UM_PER_MIL
        height = abs(y1 - y0) / UM_PER_MIL
        return QRectF(-width / 2, -height / 2, width, height)

    def boundingRect(self) -> QRectF:
        return self._chip_rect().adjusted(-10.0, -10.0, 10.0, 10.0)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._chip_rect())
        return path

    def set_interactive(self, interactive: bool) -> None:
        self.setFlag(QGraphicsItem.ItemIsMovable, interactive)
        self.setFlag(QGraphicsItem.ItemIsSelectable, interactive)
        if not interactive:
            self.setSelected(False)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        outline = self._chip_rect()
        painter.setPen(QPen(QColor("#a9b8c6"), 0.12))
        painter.setBrush(QColor("#000000"))
        painter.drawRect(outline)
        if not self.preview.isNull():
            painter.drawPixmap(outline, self.preview, QRectF(self.preview.rect()))

        painter.setPen(QPen(QColor("#ffe066"), 0.16))
        painter.setBrush(QColor(255, 135, 0, 105))
        for path in self.pad_paths.values():
            painter.drawPath(path)

        if self.isSelected():
            painter.setPen(QPen(QColor("#ff4d6d"), 0.25))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(outline.adjusted(-0.3, -0.3, 0.3, 0.3))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.ItemRotationHasChanged:
            for label in self.label_items.values():
                label.setRotation(-self.rotation())
        if change in (QGraphicsItem.ItemPositionHasChanged, QGraphicsItem.ItemRotationHasChanged):
            if self.changed:
                self.changed()
        return result

    def set_pending_pad(self, name: str | None) -> None:
        for pad_name, hit in self.hit_items.items():
            pending = pad_name == name
            hit.set_pending(pending)
            self.label_items[pad_name].set_pending(pending)

    def set_pad_labels_visible(self, visible: bool) -> None:
        for label in self.label_items.values():
            label.setVisible(visible)
        for leader in self.leader_items:
            leader.setVisible(visible)

    def pad_scene_position(self, name: str) -> QPointF:
        return self.mapToScene(self.pad_local[name])

    def nearest_pad(self, scene_pos: QPointF, max_distance: float) -> str | None:
        best_name = None
        best_distance = max_distance
        for name in self.pad_local:
            distance = _distance(self.pad_scene_position(name), scene_pos)
            if distance < best_distance:
                best_name = name
                best_distance = distance
        return best_name


class BondWireItem(QGraphicsPathItem):
    def __init__(
        self,
        index: int,
        chip_pad: str,
        board_pad: str,
        color: str = "#ff2d8d",
        width_mil: float = 0.18,
        endpoint_changed: Callable[[str, QPointF], None] | None = None,
    ):
        super().__init__()
        self.index = index
        self.chip_pad = chip_pad
        self.board_pad = board_pad
        self.endpoint_changed = endpoint_changed
        self.syncing_handles = False
        self.label = QGraphicsSimpleTextItem(str(index), self)
        self.label.setFont(QFont("Arial", 8, QFont.Bold))
        self.label.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.setBrush(QBrush(Qt.NoBrush))
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(40)
        self.setToolTip(f"{index}: {chip_pad} -> {board_pad}")
        self.chip_handle = BondEndpointHandle("chip", self)
        self.board_handle = BondEndpointHandle("board", self)
        self.set_style(color, width_mil)

    def set_style(self, color: str, width_mil: float) -> None:
        qcolor = QColor(color)
        self.label.setBrush(qcolor)
        self.setPen(QPen(qcolor, width_mil))
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        if self.isSelected():
            highlight = QPen(QColor("#00ffff"), max(self.pen().widthF() * 2.2, 0.45))
            painter.setPen(highlight)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self.path())
        painter.setPen(self.pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(1.3, self.pen().widthF() * 4))
        return stroker.createStroke(self.path())

    def update_endpoints(self, start: QPointF, end: QPointF) -> None:
        self.syncing_handles = True
        self.chip_handle.setPos(start)
        self.board_handle.setPos(end)
        self.syncing_handles = False
        self._update_path(start, end)

    def update_curve(self, points: list[QPointF]) -> None:
        if len(points) < 2:
            return
        self.syncing_handles = True
        self.chip_handle.setPos(points[0])
        self.board_handle.setPos(points[-1])
        self.syncing_handles = False
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        self.setPath(path)
        self.label.setPos(path.pointAtPercent(0.5))

    def endpoint_moved(self, endpoint: str, scene_pos: QPointF) -> None:
        if self.syncing_handles:
            return
        start = self.chip_handle.scenePos()
        end = self.board_handle.scenePos()
        self._update_path(start, end)
        if self.endpoint_changed:
            self.endpoint_changed(endpoint, scene_pos)

    def _update_path(self, start: QPointF, end: QPointF) -> None:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = max(math.hypot(dx, dy), 0.001)
        normal = QPointF(-dy / length, dx / length)
        bow = min(max(length * 0.12, 1.0), 5.0)
        control1 = QPointF(start.x() + dx * 0.33, start.y() + dy * 0.33) + normal * bow
        control2 = QPointF(start.x() + dx * 0.66, start.y() + dy * 0.66) + normal * bow
        path = QPainterPath(start)
        path.cubicTo(control1, control2, end)
        self.setPath(path)
        self.label.setPos(path.pointAtPercent(0.5))


class BondEndpointHandle(QGraphicsObject):
    def __init__(self, endpoint: str, owner: BondWireItem):
        super().__init__(owner)
        self.endpoint = endpoint
        self.owner = owner
        self.radius = 0.75
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(45)
        self.setToolTip(f"拖动调整 {endpoint} 端点")

    def boundingRect(self) -> QRectF:
        return QRectF(-self.radius, -self.radius, self.radius * 2, self.radius * 2)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.boundingRect())
        return path

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.owner.endpoint_moved(self.endpoint, self.scenePos())
        return result

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        color = QColor("#00ffff") if self.isUnderMouse() else QColor("#fff4ba")
        painter.setPen(QPen(QColor("#111111"), 0.12))
        painter.setBrush(color)
        painter.drawEllipse(self.boundingRect())


class FreeEndpointMarkerItem(QGraphicsObject):
    def __init__(self, scene_pos: QPointF):
        super().__init__()
        self.radius = 0.9
        self.setPos(scene_pos)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setZValue(46)
        self.setToolTip("自由连接端点")

    def boundingRect(self) -> QRectF:
        return QRectF(-self.radius, -self.radius, self.radius * 2, self.radius * 2)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setPen(QPen(QColor("#111111"), 0.15))
        painter.setBrush(QColor("#ffe600"))
        painter.drawEllipse(self.boundingRect())
        painter.setPen(QPen(QColor("#111111"), 0.12))
        painter.drawLine(QPointF(-0.55, 0), QPointF(0.55, 0))
        painter.drawLine(QPointF(0, -0.55), QPointF(0, 0.55))


def _distance(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())
