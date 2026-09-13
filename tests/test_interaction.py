import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PyQt5.QtGui import QKeySequence, QMouseEvent
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


def test_manual_board_pads_can_be_added_moved_aligned_distributed_and_exported(tmp_path):
    app = QApplication.instance() or QApplication([])
    project_path = tmp_path / "manual.bondwire.json"
    script_path = tmp_path / "manual_ad26.pas"
    window = MainWindow()

    for number, x, y in (("M1", 0.0, 0.0), ("M2", 30.0, 10.0), ("M3", 90.0, 25.0)):
        window.manual_pad_number.setText(number)
        window.manual_pad_width.setValue(10.0)
        window.manual_pad_height.setValue(4.0)
        window.manual_pad_shape.setCurrentText("rect")
        window.add_manual_pad_from_controls()
        item = window.board_items[number]
        item.pad.x_mil = x
        item.pad.y_mil = y
        item.sync_from_pad()

    assert window.board is not None
    assert window.project.manual_board_pads == [window.board_items[name].pad for name in ("M1", "M2", "M3")]
    assert window.board_items["M1"].flags() & QGraphicsItem.ItemIsMovable

    window.board_items["M1"].setPos(QPointF(5.0, 6.0))
    assert (window.board_items["M1"].pad.x_mil, window.board_items["M1"].pad.y_mil) == (5.0, 6.0)

    window.scene.clearSelection()
    for name in ("M1", "M2", "M3"):
        window.board_items[name].setSelected(True)
    window.align_selected_manual_pads("top")
    tops = {
        round(item.pad.y_mil - item.pad.height_mil / 2, 6)
        for item in (window.board_items["M1"], window.board_items["M2"], window.board_items["M3"])
    }
    assert len(tops) == 1

    for name, x in (("M1", 0.0), ("M2", 30.0), ("M3", 90.0)):
        window.board_items[name].pad.x_mil = x
        window.board_items[name].sync_from_pad()
    window.distribute_selected_manual_pads("x")
    centers = [window.board_items[name].pad.x_mil for name in ("M1", "M2", "M3")]
    assert centers == [0.0, 45.0, 90.0]

    window.manual_pad_spacing.setValue(20.0)
    window.distribute_selected_manual_pads("x")
    centers = [window.board_items[name].pad.x_mil for name in ("M1", "M2", "M3")]
    assert centers == [0.0, 20.0, 40.0]

    window.export_ad26_script(str(script_path))
    script = script_path.read_text(encoding="utf-8")
    assert "CurrentLib" not in script
    assert "IPCB_LibComponent" not in script
    assert "Board : IPCB_Board;" in script
    assert "Board := PCBServer.GetCurrentPCBBoard;" in script
    assert "If Not Board.IsLibrary Then" in script
    assert "PCBServer.CreatePCBLibComp" not in script
    assert "Pad.Name := 'M1'" in script
    assert "Pad.Mode := ePadMode_Simple;" in script
    assert "Pad.HoleSize := MilsToCoord(0);" in script
    assert "Board.AddPCBObject(Pad);" in script
    assert "Component.AddPCBObject(Pad);" not in script
    assert "SendMessageToRobots" not in script
    assert "I_ObjectAddress" not in script
    assert "PCBServer.PreProcess" not in script
    assert "PCBObjectFactory(eComponentObject" not in script
    assert "\nBegin\n    Create_GDS_BondWire_Reference_Footprint;" not in script
    assert "Additional Options > Pad Numbers" in script
    assert "M3,40.000000" in script

    window.save_project(str(project_path))
    restored = MainWindow()
    restored.open_project(str(project_path))
    assert set(restored.board_items) == {"M1", "M2", "M3"}
    assert all(item.pad.manual for item in restored.board_items.values())

    restored.close()
    window.close()
    app.processEvents()


def test_manual_pad_position_color_and_mm_controls_update_selection():
    app = QApplication.instance() or QApplication([])
    mil_per_mm = 1000.0 / 25.4
    window = MainWindow()

    window.manual_pad_unit.setCurrentText("mm")
    window.manual_pad_number.setText("MM1")
    window.manual_pad_x.setValue(1.0)
    window.manual_pad_y.setValue(2.0)
    window.manual_pad_width.setValue(0.5)
    window.manual_pad_height.setValue(0.25)
    window.manual_pad_color = "#00ff00"
    window._update_manual_pad_color_button()
    window.add_manual_pad_from_controls()

    item = window.board_items["MM1"]
    assert item.pad.manual
    assert item.pad.fill_color == "#00ff00"
    assert item.pad.x_mil == pytest.approx(mil_per_mm)
    assert item.pad.y_mil == pytest.approx(2.0 * mil_per_mm)
    assert item.pad.width_mil == pytest.approx(0.5 * mil_per_mm)

    item.setPos(QPointF(3.0 * mil_per_mm, 4.0 * mil_per_mm))
    assert window.manual_pad_x.value() == pytest.approx(3.0)
    assert window.manual_pad_y.value() == pytest.approx(4.0)

    window.manual_pad_x.setValue(5.0)
    window.manual_pad_y.setValue(6.0)
    window.manual_pad_color = "#0000ff"
    window._update_manual_pad_color_button()
    window.apply_manual_pad_controls_to_selection()
    assert item.pad.x_mil == pytest.approx(5.0 * mil_per_mm)
    assert item.pad.y_mil == pytest.approx(6.0 * mil_per_mm)
    assert item.pad.fill_color == "#0000ff"
    window.manual_pad_spacing.setValue(0.5)
    assert window._display_to_mil(window.manual_pad_spacing.value()) == pytest.approx(0.5 * mil_per_mm)

    window.close()
    app.processEvents()


def test_pad_editor_generates_signed_number_and_xy_steps():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    editor = window.pad_editor_dialog

    window.show_manual_pad_editor("generate")
    assert editor.isVisible()
    assert editor.mode() == "generate"
    assert editor.generate_button.isEnabled()
    assert not editor.update_button.isEnabled()

    window.manual_pad_number.setText("PAD03")
    window.manual_pad_count.setValue(3)
    window.manual_pad_delta_number_enabled.setChecked(True)
    window.manual_pad_delta_number.setValue(-1)
    window.manual_pad_delta_x_enabled.setChecked(True)
    window.manual_pad_delta_x.setValue(12.5)
    window.manual_pad_delta_y_enabled.setChecked(True)
    window.manual_pad_delta_y.setValue(-4.0)
    window.add_manual_pad_from_controls()

    assert set(window.board_items) == {"PAD03", "PAD02", "PAD01"}
    assert window.board_items["PAD03"].pad.x_mil == pytest.approx(0.0)
    assert window.board_items["PAD02"].pad.x_mil == pytest.approx(12.5)
    assert window.board_items["PAD01"].pad.x_mil == pytest.approx(25.0)
    assert window.board_items["PAD01"].pad.y_mil == pytest.approx(-8.0)

    editor.close()
    window.close()
    app.processEvents()


def test_pad_number_steps_support_negative_sign_and_cross_zero():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.pad_editor_dialog.set_mode("generate")

    window.manual_pad_number.setText("PAD-01")
    window.manual_pad_count.setValue(3)
    window.manual_pad_delta_number_enabled.setChecked(True)
    window.manual_pad_delta_number.setValue(-1)
    window.add_manual_pad_from_controls()
    assert set(window.board_items) == {"PAD-01", "PAD-02", "PAD-03"}

    window.manual_pad_number.setText("-1")
    window.manual_pad_count.setValue(1)
    window.manual_pad_delta_number.setValue(1)
    window.add_single_manual_pad_from_controls()
    assert "-1" in window.board_items
    assert window.manual_pad_number.text() == "0"
    window.add_single_manual_pad_from_controls()
    assert "0" in window.board_items
    assert window.manual_pad_number.text() == "1"

    window.close()
    app.processEvents()


def test_single_pad_button_ignores_batch_count_and_advances_enabled_steps():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    editor = window.pad_editor_dialog
    editor.set_mode("generate")

    window.manual_pad_number.setText("S05")
    window.manual_pad_count.setValue(20)
    window.manual_pad_x.setValue(10.0)
    window.manual_pad_y.setValue(30.0)
    window.manual_pad_delta_number_enabled.setChecked(True)
    window.manual_pad_delta_number.setValue(-1)
    window.manual_pad_delta_x_enabled.setChecked(True)
    window.manual_pad_delta_x.setValue(2.5)
    window.manual_pad_delta_y_enabled.setChecked(True)
    window.manual_pad_delta_y.setValue(-3.0)

    editor.single_generate_button.click()
    assert set(window.board_items) == {"S05"}
    assert window.board_items["S05"].pad.x_mil == pytest.approx(10.0)
    assert window.board_items["S05"].pad.y_mil == pytest.approx(30.0)
    assert window.manual_pad_number.text() == "S04"
    assert window.manual_pad_x.value() == pytest.approx(12.5)
    assert window.manual_pad_y.value() == pytest.approx(27.0)

    editor.single_generate_button.click()
    assert set(window.board_items) == {"S05", "S04"}
    assert window.board_items["S04"].pad.x_mil == pytest.approx(12.5)
    assert window.board_items["S04"].pad.y_mil == pytest.approx(27.0)

    window.close()
    app.processEvents()


def test_batch_pad_edit_preserves_and_refreshes_bondwire_relationship():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")

    window.pad_editor_dialog.set_mode("generate")
    window.manual_pad_number.setText("P1")
    window.manual_pad_count.setValue(2)
    window.manual_pad_delta_number_enabled.setChecked(True)
    window.manual_pad_delta_number.setValue(1)
    window.manual_pad_delta_x_enabled.setChecked(True)
    window.manual_pad_delta_x.setValue(20.0)
    window.add_manual_pad_from_controls()
    window.add_bond("NGNDA", "P1")

    window.pad_editor_dialog.set_mode("edit")
    window.scene.clearSelection()
    window.board_items["P1"].setSelected(True)
    window.board_items["P2"].setSelected(True)
    window.manual_pad_number.setText("P10")
    window.manual_pad_delta_number_enabled.setChecked(True)
    window.manual_pad_delta_number.setValue(-1)
    window.manual_pad_x.setValue(100.0)
    window.manual_pad_delta_x_enabled.setChecked(True)
    window.manual_pad_delta_x.setValue(15.0)
    window.apply_manual_pad_controls_to_selection()

    assert set(window.board_items) == {"P10", "P09"}
    assert window.project.bonds[0].board_pad == "P10"
    assert window.table.item(0, 2).text() == "P10"
    assert window.bond_items[0].board_handle.scenePos() == window.board_items["P10"].scenePos()
    assert window.board_items["P09"].pad.x_mil == pytest.approx(115.0)

    window.close()
    app.processEvents()


def test_ctrl_z_undoes_pad_generation_and_bondwire_edits():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.undo_action.shortcut() == QKeySequence.Undo

    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.pad_editor_dialog.set_mode("generate")
    window.manual_pad_number.setText("U1")
    window.add_manual_pad_from_controls()
    assert "U1" in window.board_items
    assert window.undo_action.isEnabled()

    window.add_bond("NGNDA", "U1")
    assert len(window.project.bonds) == 1
    window.undo_action.trigger()
    assert window.project.bonds == []
    assert "U1" in window.board_items

    window.undo_action.trigger()
    assert "U1" not in window.board_items
    assert window.project.manual_board_pads == []
    assert not window.undo_action.isEnabled()
    window.close()
    app.processEvents()


def test_undo_restores_pad_drag_and_bondwire_endpoint():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.manual_pad_number.setText("U1")
    window.add_manual_pad_from_controls()
    window.add_bond("NGNDA", "U1")
    window.clear_undo_history()

    pad = window.board_items["U1"]
    window.begin_undo_transaction("移动 PAD U1")
    pad.setPos(QPointF(40.0, 25.0))
    window.finish_undo_transaction()
    assert pad.scenePos() == QPointF(40.0, 25.0)
    window.undo_last_action()
    assert window.board_items["U1"].scenePos() == QPointF(0.0, 0.0)
    assert window.bond_items[0].board_handle.scenePos() == QPointF(0.0, 0.0)

    bond = window.project.bonds[0]
    original_offset = bond.board_offset_x_mil
    window.begin_undo_transaction("调整 BondWire 端点")
    window.bond_items[0].board_handle.setPos(QPointF(8.0, 0.0))
    window.finish_undo_transaction()
    assert bond.board_offset_x_mil != original_offset
    window.undo_last_action()
    assert window.project.bonds[0].board_offset_x_mil == original_offset
    window.close()
    app.processEvents()


def test_chip_can_be_hidden_without_losing_bonds_and_visibility_is_undoable(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.manual_pad_number.setText("V1")
    window.add_manual_pad_from_controls()
    window.add_bond("NGNDA", "V1")
    window.clear_undo_history()

    window.chip_visibility_action.setChecked(False)
    assert not window.project.chip_visible
    assert not window.chip_item.isVisible()
    assert len(window.project.bonds) == 1
    assert len(window.bond_items) == 1

    window.undo_last_action()
    assert window.project.chip_visible
    assert window.chip_visibility_action.isChecked()
    assert window.chip_item.isVisible()
    assert len(window.project.bonds) == 1

    window.clear_undo_history()
    window.chip_x.setValue(12.0)
    assert window.project.chip_x_mil == 12.0
    window.undo_last_action()
    assert window.project.chip_x_mil == 0.0
    assert window.chip_item.pos().x() == 0.0

    window.chip_visibility_action.setChecked(False)
    project_path = tmp_path / "hidden-chip.bondwire.json"
    window.save_project(str(project_path))
    restored = MainWindow()
    restored.open_project(str(project_path))
    assert not restored.project.chip_visible
    assert not restored.chip_visibility_action.isChecked()
    assert not restored.chip_item.isVisible()
    assert len(restored.project.bonds) == 1

    restored.close()
    window.close()
    app.processEvents()


def test_manual_pad_bounding_rect_covers_selection_outline():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.manual_pad_number.setText("B1")
    window.manual_pad_width.setValue(10.0)
    window.manual_pad_height.setValue(4.0)
    window.add_manual_pad_from_controls()

    item = window.board_items["B1"]
    assert item.boundingRect().contains(item._rect(1.0))
    assert window.view.viewportUpdateMode() == QGraphicsView.BoundingRectViewportUpdate

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
