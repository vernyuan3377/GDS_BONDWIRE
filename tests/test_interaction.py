import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QGraphicsItem, QGraphicsView

import bondwire_app.main_window as main_window_module
from bondwire_app.main_window import MainWindow


def test_clicking_external_chip_label_then_board_pad_creates_bond():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.set_mode(True)

    chip_label = window.chip_item.label_items["NGNDA"]
    window.handle_canvas_click(chip_label.scenePos())
    assert window.pending_endpoint == ("chip", "NGNDA")

    window.handle_canvas_click(window.board_items["1"].scenePos())
    assert [(bond.chip_pad, bond.board_pad) for bond in window.project.bonds] == [("NGNDA", "1")]
    window.close()
    app.processEvents()


def test_double_clicking_non_pad_area_creates_free_endpoint_and_connects_to_pad():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.set_mode(True)

    free_pos = QPointF(75.0, 65.0)
    window.handle_canvas_double_click(free_pos)
    assert window.pending_endpoint == ("free", "FREE")
    assert window.pending_free_item is not None
    assert window.pending_free_item.scenePos() == free_pos

    window.handle_canvas_click(window.board_items["1"].scenePos())
    bond = window.project.bonds[0]
    assert bond.chip_endpoint_type == "free"
    assert bond.board_endpoint_type == "pad"
    assert (bond.chip_free_x_mil, bond.chip_free_y_mil) == (75.0, 65.0)
    assert bond.board_pad == "1"

    wire = window.bond_items[0]
    wire.chip_handle.setPos(QPointF(80.0, 70.0))
    assert (bond.chip_free_x_mil, bond.chip_free_y_mil) == (80.0, 70.0)

    window._set_pending_endpoint(None)
    window.handle_canvas_double_click(window.board_items["2"].scenePos())
    assert window.pending_endpoint is None
    window.close()
    app.processEvents()


def test_real_mouse_double_click_creates_pending_free_endpoint():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.set_mode(True)
    window.fit_scene()
    app.processEvents()

    free_pos = QPointF(46.0, 0.0)
    assert window._endpoint_at(free_pos, include_nearest=False) is None
    QTest.mouseDClick(
        window.view.viewport(),
        Qt.LeftButton,
        pos=window.view.mapFromScene(free_pos),
    )
    app.processEvents()

    assert window.pending_endpoint == ("free", "FREE")
    assert window.pending_free_item is not None
    window.close()
    app.processEvents()


def test_double_clicking_two_non_pad_areas_creates_free_to_free_wire():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.set_mode(True)

    window.handle_canvas_double_click(QPointF(70.0, 60.0))
    window.handle_canvas_double_click(QPointF(85.0, 75.0))

    bond = window.project.bonds[0]
    assert bond.chip_endpoint_type == "free"
    assert bond.board_endpoint_type == "free"
    assert window.pending_endpoint is None
    window.close()
    app.processEvents()


def test_wire_does_not_block_pad_connection_and_table_can_delete_it():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.add_bond("NGNDA", "1")
    window.set_mode(True)

    wire = window.bond_items[0]
    midpoint = wire.path().pointAtPercent(0.5)
    assert window._bond_at(midpoint) is wire
    assert window._endpoint_at(midpoint, False) == ("board", "21")
    window.handle_canvas_click(midpoint)
    assert window.pending_endpoint == ("board", "21")
    assert not wire.isSelected()

    window._set_pending_endpoint(None)
    window.show()
    window.fit_scene()
    app.processEvents()
    handle_point = window.view.mapFromScene(wire.board_handle.scenePos())
    QTest.mouseClick(window.view.viewport(), Qt.LeftButton, pos=handle_point)
    app.processEvents()
    assert window.pending_endpoint == ("board", "1")

    window._set_pending_endpoint(None)
    drag_point = handle_point + QPoint(30, 20)
    QTest.mousePress(window.view.viewport(), Qt.LeftButton, pos=handle_point)
    window.view.mouseMoveEvent(
        QMouseEvent(
            QEvent.MouseMove,
            QPointF(drag_point),
            Qt.NoButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
    )
    window.view.mouseReleaseEvent(
        QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(drag_point),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
    )
    assert window.project.bonds[0].board_offset_x_mil != 0.0
    assert window.pending_endpoint is None

    window.table.selectRow(0)
    window.delete_selected_bonds()
    assert window.project.bonds == []
    assert window.bond_items == []
    window.close()
    app.processEvents()


def test_wire_endpoints_can_be_dragged_and_follow_chip_transform():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.add_bond("NGNDA", "1")

    wire = window.bond_items[0]
    old_chip_endpoint = wire.chip_handle.scenePos()
    wire.chip_handle.setPos(old_chip_endpoint + QPointF(2.0, 3.0))
    bond = window.project.bonds[0]
    assert bond.chip_offset_x_mil == 2.0
    assert bond.chip_offset_y_mil == 3.0

    adjusted_endpoint = wire.chip_handle.scenePos()
    window.chip_x.setValue(window.chip_x.value() + 5.0)
    assert wire.chip_handle.scenePos().x() == adjusted_endpoint.x() + 5.0
    assert wire.chip_handle.scenePos().y() == adjusted_endpoint.y()
    window.close()
    app.processEvents()


def test_pcb_rotation_moves_native_preview_pads_bonds_and_3d_plane():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.add_bond("NGNDA", "1")

    pad_before = window.board_items["1"].scenePos()
    endpoint_before = window.bond_items[0].board_handle.scenePos()
    window.pcb_rotation.setValue(90.0)
    pad_after = window.board_items["1"].scenePos()

    assert window.project.pcb_rotation_deg == 90.0
    assert window.board_assembly_item.rotation() == 90.0
    assert pad_after != pad_before
    assert window.bond_items[0].board_handle.scenePos() == pad_after
    assert window.bond_items[0].board_handle.scenePos() != endpoint_before
    assert window._endpoint_at(pad_after, include_nearest=False) == ("board", "1")

    window.show_3d_view()
    app.processEvents()
    board_corners = window.three_d_dialog.view._plane_corners()[:4]
    preview_rect = window.board_preview_item.boundingRect()
    expected = window.board_preview_item.mapToScene(preview_rect.topLeft())
    assert board_corners[0][:2] == (expected.x(), expected.y())

    window.close()
    app.processEvents()


def test_pcblib_orientation_matches_native_pad_number_order():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")

    # Native Z_PATH orientation has right-side pads 1..6 from top to bottom.
    assert [
        window.board_items[str(number)].scenePos().y()
        for number in range(1, 7)
    ] == sorted(
        window.board_items[str(number)].scenePos().y()
        for number in range(1, 7)
    )
    # Top-side pads are 17..20 from left to right.
    assert [
        window.board_items[str(number)].scenePos().x()
        for number in range(17, 21)
    ] == sorted(
        window.board_items[str(number)].scenePos().x()
        for number in range(17, 21)
    )
    window.close()
    app.processEvents()


def test_project_open_restores_pcb_rotation(tmp_path):
    app = QApplication.instance() or QApplication([])
    project_path = tmp_path / "rotated.bondwire.json"
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.pcb_rotation.setValue(37.5)
    window.save_project(str(project_path))
    window.close()

    restored = MainWindow()
    restored.open_project(str(project_path))
    assert restored.project.pcb_rotation_deg == 37.5
    assert restored.pcb_rotation.value() == 37.5
    assert restored.board_assembly_item.rotation() == 37.5
    restored.close()
    app.processEvents()


def test_draw_mode_disables_chip_frame_and_metal_does_not_block_pads():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/XY_DRIVE.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.set_mode(True)

    assert window.view.dragMode() == QGraphicsView.NoDrag
    assert window.board_preview_item is not None
    assert window.board_preview_item.acceptedMouseButtons() == Qt.NoButton
    assert all(not item.native_rendered or item.acceptedMouseButtons() != Qt.NoButton for item in window.board_items.values())
    assert not window.chip_item.flags() & QGraphicsItem.ItemIsMovable
    assert not window.chip_item.flags() & QGraphicsItem.ItemIsSelectable
    first_pad = next(iter(window.board_items.values()))
    assert window._endpoint_at(first_pad.scenePos()) == ("board", first_pad.pad.number)
    window.set_mode(False)
    assert window.view.dragMode() == QGraphicsView.NoDrag
    assert window.chip_item.flags() & QGraphicsItem.ItemIsMovable
    window.close()
    app.processEvents()


def test_chip_pad_labels_are_arranged_on_their_nearest_edge():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    chip = window.chip_item
    outline = chip._chip_rect()

    assert {"left", "right", "top", "bottom"} <= set(chip.label_sides.values())
    for name, side in chip.label_sides.items():
        label_pos = chip.label_items[name].pos()
        if side == "left":
            assert label_pos.x() < outline.left()
        elif side == "right":
            assert label_pos.x() > outline.right()
        elif side == "top":
            assert label_pos.y() < outline.top()
        else:
            assert label_pos.y() > outline.bottom()
    for side in ("left", "right", "top", "bottom"):
        labels = [
            chip.label_items[name]
            for name, label_side in chip.label_sides.items()
            if label_side == side
        ]
        for index, first in enumerate(labels):
            first_rect = first.mapRectToParent(first.boundingRect())
            for second in labels[index + 1 :]:
                second_rect = second.mapRectToParent(second.boundingRect())
                assert not first_rect.intersects(second_rect)
    window.close()
    app.processEvents()


def test_chip_pad_labels_remain_upright_when_chip_rotates():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")

    window.chip_rotation.setValue(73.0)
    assert window.chip_item.rotation() == 73.0
    assert all(label.rotation() == -73.0 for label in window.chip_item.label_items.values())

    window.chip_rotation.setValue(-28.5)
    assert all(label.rotation() == 28.5 for label in window.chip_item.label_items.values())
    window.close()
    app.processEvents()


def test_wire_style_updates_and_pdf_export_restores_labels(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.add_bond("NGNDA", "1")

    window.project.bondwire_color = "#00aa55"
    window.wire_width.setValue(0.5)
    window.apply_wire_style()

    wire = window.bond_items[0]
    assert not wire.chip_handle.flags() & QGraphicsItem.ItemIsSelectable
    assert not wire.board_handle.flags() & QGraphicsItem.ItemIsSelectable
    assert wire.pen().color().name() == "#00aa55"
    assert wire.pen().widthF() == 0.5
    assert wire.label.brush().color().name() == "#00aa55"

    class FakePrinter:
        HighResolution = 1
        PdfFormat = 2
        A3 = 3
        Landscape = 4
        DevicePixel = 5

        def __init__(self, _mode):
            self.path = ""

        def setOutputFormat(self, _format):
            pass

        def setOutputFileName(self, path):
            self.path = path
            Path(path).write_bytes(b"%PDF-test")

        def setPageSize(self, _size):
            pass

        def setOrientation(self, _orientation):
            pass

        def setFullPage(self, _full_page):
            pass

        def pageRect(self, _unit):
            return QRectF(0, 0, 1200, 800)

    class FakePainter:
        def __init__(self, _printer):
            pass

        def setFont(self, _font):
            pass

        def drawText(self, *_args):
            pass

        def end(self):
            pass

    labels_hidden_during_render = []

    def fake_render(*_args):
        labels_hidden_during_render.append(
            all(not label.isVisible() for label in window.chip_item.label_items.values())
        )

    monkeypatch.setattr(main_window_module, "QPrinter", FakePrinter)
    monkeypatch.setattr(main_window_module, "QPainter", FakePainter)
    monkeypatch.setattr(window.scene, "render", fake_render)
    monkeypatch.setattr(window, "_paint_pdf_table", lambda *_args: None)

    window.pdf_include_labels.setChecked(False)
    pdf_path = tmp_path / "without_chip_pad_labels.pdf"
    window.export_pdf(str(pdf_path))

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert labels_hidden_during_render == [True]
    assert all(label.isVisible() for label in window.chip_item.label_items.values())
    assert all(leader.isVisible() for leader in window.chip_item.leader_items)
    window.close()
    app.processEvents()
