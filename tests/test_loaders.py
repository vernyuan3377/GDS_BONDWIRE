from pathlib import Path
import xml.etree.ElementTree as ET

from bondwire_app.loaders import load_gds, load_pcblib


ROOT = Path(__file__).resolve().parents[1]


def test_sample_pcblib_loads_pads():
    board = load_pcblib(ROOT / "DATA" / "PCB_Outline" / "Z_PATH.PcbLib")
    assert board.footprint_name == "Z_PATH_CHIP"
    assert len(board.pads) == 21
    assert {pad.number for pad in board.pads} == {str(index) for index in range(1, 22)}


def test_sample_gds_recognizes_named_edge_pads():
    chip = load_gds(ROOT / "DATA" / "GDS" / "Z_BIAS_TOP_ALL.gds")
    names = {pad.name for pad in chip.pads}
    assert chip.cell_name == "Z_BIAS_TOP_ALL"
    assert chip.search_depth == 10
    assert (chip.cb_layer, chip.cb_datatype) == (76, 0)
    assert len(chip.pads) == 20
    assert {"NGNDA", "VCC_HV", "BIAS_OUT", "CAP_SENSE", "NVDD"} <= names

    nvdd = next(pad for pad in chip.pads if pad.name == "NVDD")
    assert 15 < nvdd.x_um < 80
    assert nvdd.y_um > 400
    xs = [point[0] for point in nvdd.polygon_um]
    ys = [point[1] for point in nvdd.polygon_um]
    assert round(max(xs) - min(xs), 3) == 56.0
    assert round(max(ys) - min(ys), 3) == 56.0


def test_sample_pcblib_uses_altium_corner_radius():
    board = load_pcblib(ROOT / "DATA" / "PCB_Outline" / "Z_PATH.PcbLib")
    center_pad = next(pad for pad in board.pads if pad.number == "21")
    assert center_pad.corner_radius_percent == 50


def test_pcblib_uses_native_primitive_mask():
    board = load_pcblib(ROOT / "DATA" / "PCB_Outline" / "XY_DRIVE.PcbLib")
    assert board.metal_layers == ["Top Layer"]
    assert board.native_primitive_count == 46
    assert board.preview_svg.startswith(b"<")
    assert b"<ns0:text" not in board.preview_svg
    assert board.first_metal_layer == "Top Layer"
    assert board.first_metal_svg.startswith(b"<")
    assert board.first_metal_bbox_mil is not None
    root = ET.fromstring(board.first_metal_svg)
    groups = {
        child.attrib.get("id")
        for child in root
        if child.tag.endswith("g")
    }
    assert groups == {"Top_Layer"}
    assert board.preview_bbox_mil is not None
