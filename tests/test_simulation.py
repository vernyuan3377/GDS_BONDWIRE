import csv
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication

from bondwire_app.main_window import MainWindow
from bondwire_app.models import Bond
from bondwire_app.simulation import (
    default_control_point,
    export_simulation_package,
    polyline_length,
    quadratic_length,
    sample_quadratic,
)
from bondwire_app.three_d import Bond3DDialog
import gdstk


def test_quadratic_wire_has_real_3d_length():
    start = (0.0, 0.0, 5.0)
    end = (100.0, 0.0, 0.0)
    control = default_control_point(start, end)
    points = sample_quadratic(start, control, end)

    assert control[2] > start[2]
    length = quadratic_length(start, control, end)
    assert length > 100.0
    assert abs(length - polyline_length(sample_quadratic(start, control, end, 4097))) < 0.001


def test_simulation_package_contains_gds_xyz_and_hfss_script(tmp_path):
    bond = Bond(
        chip_pad="VDD",
        board_pad="1",
        control_x_mil=50.0,
        control_y_mil=5.0,
        control_z_mil=20.0,
        wire_diameter_um=22.0,
    )
    paths = export_simulation_package(
        tmp_path,
        [bond],
        lambda _bond: ((0.0, 0.0, 5.0), (100.0, 0.0, 0.0)),
        lambda current, endpoint: current.chip_pad if endpoint == "chip" else current.board_pad,
    )

    assert {path.name for path in paths} == {
        "layout.gds",
        "bondwires_3d.csv",
        "manifest.json",
        "hfss_import.py",
        "README.txt",
    }
    library = gdstk.read_gds(str(tmp_path / "layout.gds"))
    assert library.cells[0].polygons
    with (tmp_path / "bondwires_3d.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 33
    assert max(float(row["z_mil"]) for row in rows) > 5.0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["wires"][0]["diameter_um"] == 22.0
    assert manifest["wires"][0]["length_mil"] > 100.0
    assert "CreatePolyline" in (tmp_path / "hfss_import.py").read_text(encoding="utf-8")


def test_3d_dialog_changes_control_point_and_length():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.add_bond("NGNDA", "1")
    bond = window.project.bonds[0]
    initial_length = window._bond_length_3d(bond)

    dialog = Bond3DDialog(window)
    control = window._bond_middle_point_3d(bond)
    assert window._bond_points_3d(bond)[16] == control
    old_2d_midpoint = window.bond_items[0].path().pointAtPercent(0.5)
    dialog.set_middle_point(control[0] + 20.0, control[1], control[2])
    new_2d_midpoint = window.bond_items[0].path().pointAtPercent(0.5)
    assert new_2d_midpoint.x() != old_2d_midpoint.x()

    control = window._bond_middle_point_3d(bond)
    dialog.set_middle_point(control[0], control[1], control[2] + 50.0)
    dialog.diameter.setValue(30.0)

    assert window._bond_middle_point_3d(bond)[2] == control[2] + 50.0
    assert bond.wire_diameter_um == 30.0
    assert window._bond_length_3d(bond) > initial_length
    target = window._bond_length_3d(bond) + 20.0
    dialog.length.setValue(target)
    assert abs(window._bond_length_3d(bond) - target) < 0.01

    dialog.show()
    app.processEvents()
    dialog.view._update_projection()
    control_before_drag = window._bond_middle_point_3d(bond)
    screen_control = dialog.view._project(control_before_drag).toPoint()
    destination = screen_control + QPoint(25, 0)
    dialog.view.mousePressEvent(
        QMouseEvent(
            QEvent.MouseButtonPress,
            QPointF(screen_control),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
    )
    dialog.view.mouseMoveEvent(
        QMouseEvent(QEvent.MouseMove, QPointF(destination), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    )
    dialog.view.mouseReleaseEvent(
        QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(destination),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
    )
    assert window._bond_middle_point_3d(bond)[:2] != control_before_drag[:2]

    dialog.view._update_projection()
    control_before_z_drag = window._bond_middle_point_3d(bond)
    screen_control = dialog.view._project(control_before_z_drag).toPoint()
    destination = screen_control + QPoint(0, -25)
    dialog.view.mousePressEvent(
        QMouseEvent(
            QEvent.MouseButtonPress,
            QPointF(screen_control),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.ShiftModifier,
        )
    )
    dialog.view.mouseMoveEvent(
        QMouseEvent(
            QEvent.MouseMove,
            QPointF(destination),
            Qt.NoButton,
            Qt.LeftButton,
            Qt.ShiftModifier,
        )
    )
    dialog.view.mouseReleaseEvent(
        QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(destination),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.ShiftModifier,
        )
    )
    assert window._bond_middle_point_3d(bond)[2] > control_before_z_drag[2]
    dialog.close()
    window.close()
    app.processEvents()


def test_3d_and_table_selection_stay_in_sync():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_pcblib_file("DATA/PCB_Outline/Z_PATH.PcbLib")
    window.load_gds_file("DATA/GDS/Z_BIAS_TOP_ALL.gds")
    window.add_bond("NGNDA", "1")
    window.add_bond("NGNDA", "2")
    window.show_3d_view()
    app.processEvents()

    window.table.selectRow(1)
    assert window.three_d_dialog.selected_index == 1
    window.three_d_dialog.select_bond(0)
    assert window.table.currentRow() == 0

    window.close()
    app.processEvents()
