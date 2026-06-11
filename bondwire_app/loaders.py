from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
if VENDOR.exists() and str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

import gdstk  # type: ignore
import pyaltiumlib  # type: ignore
import svgwrite  # type: ignore
from PIL import Image, ImageDraw
from pyaltiumlib.datatypes import Coordinate, CoordinatePoint  # type: ignore

from .models import BoardData, BoardPad, ChipData, ChipPad

METAL_LAYER_IDS = set(range(1, 33)) | set(range(39, 55)) | {74}


def _coord(value: object) -> float:
    return float(value)


def _layer_details(library, layer_id: int) -> tuple[str, str]:
    layer = next((item for item in library.Layers if item.id == layer_id), None)
    if layer is None:
        return f"Layer {layer_id}", "#808080"
    return layer.name, layer.color.to_hex()


def _render_pcblib_preview(footprint, layer_ids: set[int] | None = None):
    drawable = [record for record in footprint.Records if getattr(record, "is_drawable", False) and callable(getattr(record, "draw_svg", None)) and (layer_ids is None or int(getattr(record, "layer", 0)) in layer_ids)]
    bounds = [record.get_bounding_box() for record in drawable]
    bounds = [bound for bound in bounds if bound is not None]
    if not bounds:
        return b"", None
    min_x = min(min(_coord(bound[0].x), _coord(bound[1].x)) for bound in bounds)
    min_y = min(min(_coord(bound[0].y), _coord(bound[1].y)) for bound in bounds)
    max_x = max(max(_coord(bound[0].x), _coord(bound[1].x)) for bound in bounds)
    max_y = max(max(_coord(bound[0].y), _coord(bound[1].y)) for bound in bounds)
    margin, zoom = 10.0, 10.0
    width, height = max(max_x - min_x + margin * 2, 1.0), max(max_y - min_y + margin * 2, 1.0)
    drawing = svgwrite.Drawing(size=(width * zoom, height * zoom), profile="full")
    footprint._graphic_layers = {}
    for layer in sorted(footprint.LibFile.Layers, key=lambda item: item.drawing_order, reverse=True):
        footprint._graphic_layers[layer.id] = drawing.add(drawing.g(id=layer.svg_layer))
    offset = CoordinatePoint(Coordinate((-min_x + margin) * zoom), Coordinate((-min_y + margin) * zoom))
    for record in drawable:
        record.draw_svg(drawing, offset, zoom)
    root = ET.fromstring(drawing.tostring())
    namespace = "{http://www.w3.org/2000/svg}"
    if layer_ids is not None:
        allowed_groups = {layer.svg_layer for layer in footprint.LibFile.Layers if int(layer.id) in layer_ids}
        for child in list(root):
            if child.tag == f"{namespace}g" and child.attrib.get("id") not in allowed_groups:
                root.remove(child)
    for parent in root.iter():
        for child in list(parent):
            if child.tag == f"{namespace}text":
                parent.remove(child)
    return ET.tostring(root, encoding="utf-8"), ((min_x - margin, min_y - margin), (max_x + margin, max_y + margin))


def load_pcblib(path: str | Path) -> BoardData:
    path = str(Path(path).resolve())
    library = pyaltiumlib.read(path)
    if not library.Parts:
        raise ValueError("PcbLib 中没有封装。")
    footprint = library.Parts[0]
    pads: list[BoardPad] = []
    for record in footprint.Records:
        if record.__class__.__name__ != "PcbPad":
            continue
        pads.append(BoardPad(number=str(record.designator), x_mil=_coord(record.location.x), y_mil=_coord(record.location.y), width_mil=abs(_coord(record.size_top.x)), height_mil=abs(_coord(record.size_top.y)), rotation_deg=float(record.rotation), shape=str(getattr(record, "shape_top", "round")).lower(), layer=int(record.layer), solder_expansion_mil=abs(_coord(record.expansion_solder_mask)) if getattr(record, "expansion_manual_solder_mask", 0) == 2 else 4.0, corner_radius_percent=float(record.corner_radius_percentage[0] if getattr(record, "corner_radius_percentage", None) else 100)))
    if not pads:
        raise ValueError("PcbLib 中没有可读取的 PAD。")
    metal_layer_ids = {int(record.layer) for record in footprint.Records if int(getattr(record, "layer", 0)) in METAL_LAYER_IDS}
    preview_svg, preview_bbox = _render_pcblib_preview(footprint)
    first_metal_layer_id = min(metal_layer_ids) if metal_layer_ids else None
    first_metal_svg, first_metal_bbox = _render_pcblib_preview(footprint, {first_metal_layer_id}) if first_metal_layer_id is not None else (b"", None)
    return BoardData(path=path, footprint_name=footprint.Name, pads=pads, metal_layers=[_layer_details(library, i)[0] for i in sorted(metal_layer_ids)], native_primitive_count=sum(1 for r in footprint.Records if getattr(r, "is_drawable", False) and callable(getattr(r, "draw_svg", None))), preview_svg=preview_svg, preview_bbox_mil=preview_bbox, first_metal_layer=_layer_details(library, first_metal_layer_id)[0] if first_metal_layer_id is not None else "", first_metal_svg=first_metal_svg, first_metal_bbox_mil=first_metal_bbox)


def _polygon_center(polygon: gdstk.Polygon):
    bbox = polygon.bounding_box()
    return (float(bbox[0][0]) + float(bbox[1][0])) / 2.0, (float(bbox[0][1]) + float(bbox[1][1])) / 2.0


def _pair_labels_and_polygons(labels: list, polygons: list[gdstk.Polygon]) -> list[ChipPad]:
    if not labels:
        raise ValueError("指定的 AP Pin 层没有找到顶层 PAD 名称。")
    if not polygons:
        raise ValueError("指定的 CB 层没有找到 PAD 图形。")
    centers = [_polygon_center(polygon) for polygon in polygons]
    candidates = [((float(label.origin[0]) - px) ** 2 + (float(label.origin[1]) - py) ** 2, li, pi) for li, label in enumerate(labels) for pi, (px, py) in enumerate(centers)]
    used_labels, used_polygons, pairs = set(), set(), []
    for _, li, pi in sorted(candidates):
        if li in used_labels or pi in used_polygons:
            continue
        used_labels.add(li); used_polygons.add(pi); pairs.append((li, pi))
        if len(used_labels) == len(labels): break
    result, name_counts = [], {}
    for li, pi in pairs:
        label, polygon = labels[li], polygons[pi]
        name = str(label.text).strip() or f"PAD_{li + 1}"
        name_counts[name] = name_counts.get(name, 0) + 1
        if name_counts[name] > 1: name = f"{name}#{name_counts[name]}"
        x, y = centers[pi]
        result.append(ChipPad(name=name, x_um=x, y_um=y, polygon_um=[(float(a), float(b)) for a, b in polygon.points]))
    return result


def _render_gds_preview(cell: gdstk.Cell, bbox, resolution: int = 1400) -> bytes:
    (x0, y0), (x1, y1) = bbox
    width, height = max(x1 - x0, 0.001), max(y1 - y0, 0.001)
    image = Image.new("RGBA", (resolution, resolution), (0, 0, 0, 255)); draw = ImageDraw.Draw(image, "RGBA")
    colors = {6: "#00ff00", 25: "#00ffff", 26: "#ffff00", 30: "#00ff00", 31: "#00ffff", 32: "#ffff00", 33: "#ff2020", 34: "#ff00ff", 35: "#ffff00", 36: "#00ffff", 37: "#ffffff", 38: "#ff3030", 39: "#00ffff", 51: "#00ff00", 52: "#00ffff", 53: "#ffff00", 54: "#ff3030", 55: "#ff00ff", 56: "#00ff00", 76: "#ffff00", 111: "#ff7000", 127: "#ffffff"}
    fallback = ("#00ff00", "#00ffff", "#ff3030", "#ffff00", "#ffffff", "#ff00ff", "#2080ff")
    for polygon in sorted(cell.get_polygons(True, True, 2), key=lambda item: (item.layer in (6, 111), item.layer)):
        color = colors.get(polygon.layer, fallback[polygon.layer % len(fallback)])
        points = [((float(x) - x0) / width * (resolution - 1), (y1 - float(y)) / height * (resolution - 1)) for x, y in polygon.points]
        if len(points) < 2: continue
        p0, p1 = polygon.bounding_box(); area = (float(p1[0]) - float(p0[0])) * (float(p1[1]) - float(p0[1]))
        if polygon.layer in (6, 111) and area < width * height * 0.1: draw.polygon(points, fill=color + "55", outline=color + "ff")
        else: draw.line(points + [points[0]], fill=color + "dd", width=1)
    output = BytesIO(); image.save(output, format="PNG", optimize=True); return output.getvalue()


def load_gds(path: str | Path, cb_layer: int = 76, cb_datatype: int = 0, ap_layer: int = 126, ap_texttype: int = 0, search_depth: int = 10) -> ChipData:
    path = str(Path(path).resolve()); library = gdstk.read_gds(path); top_cells = library.top_level()
    if not top_cells: raise ValueError("GDS 中没有顶层 Cell。")
    cell = top_cells[0]; bbox = cell.bounding_box()
    if bbox is None: raise ValueError("GDS 顶层 Cell 为空。")
    deep_labels = cell.get_labels(True, search_depth, ap_layer, ap_texttype)
    labels = [label for label in cell.labels if label.layer == ap_layer and label.texttype == ap_texttype] or deep_labels
    polygons = cell.get_polygons(True, True, search_depth, cb_layer, cb_datatype)
    numeric_bbox = ((float(bbox[0][0]), float(bbox[0][1])), (float(bbox[1][0]), float(bbox[1][1])))
    return ChipData(path=path, cell_name=cell.name, bbox_um=numeric_bbox, pads=_pair_labels_and_polygons(labels, polygons), overview_polygons_um=[[(float(x), float(y)) for x, y in polygon.points] for polygon in cell.polygons[:500]], preview_png=_render_gds_preview(cell, numeric_bbox), cb_layer=cb_layer, cb_datatype=cb_datatype, ap_layer=ap_layer, ap_texttype=ap_texttype, search_depth=search_depth)


def point_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
