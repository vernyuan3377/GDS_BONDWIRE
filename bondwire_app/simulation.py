from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Callable

import gdstk  # type: ignore

from .models import Bond

UM_PER_MIL = 25.4
Point3D = tuple[float, float, float]


def default_control_point(start: Point3D, end: Point3D) -> Point3D:
    planar = math.hypot(end[0] - start[0], end[1] - start[1])
    middle = (
        (start[0] + end[0]) / 2,
        (start[1] + end[1]) / 2,
        max(start[2], end[2]) + max(5.0, planar * 0.2),
    )
    return midpoint_to_control(start, middle, end)


def bond_control_point(bond: Bond, start: Point3D, end: Point3D) -> Point3D:
    if bond.control_x_mil is None or bond.control_y_mil is None or bond.control_z_mil is None:
        return default_control_point(start, end)
    return bond.control_x_mil, bond.control_y_mil, bond.control_z_mil


def quadratic_point(start: Point3D, control: Point3D, end: Point3D, t: float) -> Point3D:
    a = (1 - t) ** 2
    b = 2 * (1 - t) * t
    c = t**2
    return (
        a * start[0] + b * control[0] + c * end[0],
        a * start[1] + b * control[1] + c * end[1],
        a * start[2] + b * control[2] + c * end[2],
    )


def midpoint_to_control(start: Point3D, middle: Point3D, end: Point3D) -> Point3D:
    return (
        2 * middle[0] - (start[0] + end[0]) / 2,
        2 * middle[1] - (start[1] + end[1]) / 2,
        2 * middle[2] - (start[2] + end[2]) / 2,
    )


def bond_midpoint(bond: Bond, start: Point3D, end: Point3D) -> Point3D:
    return quadratic_point(start, bond_control_point(bond, start, end), end, 0.5)


def sample_quadratic(start: Point3D, control: Point3D, end: Point3D, count: int = 33) -> list[Point3D]:
    points: list[Point3D] = []
    for index in range(max(count, 2)):
        t = index / (max(count, 2) - 1)
        points.append(quadratic_point(start, control, end, t))
    return points


def polyline_length(points: list[Point3D]) -> float:
    return sum(
        math.sqrt(
            (second[0] - first[0]) ** 2
            + (second[1] - first[1]) ** 2
            + (second[2] - first[2]) ** 2
        )
        for first, second in zip(points, points[1:])
    )


def quadratic_length(start: Point3D, control: Point3D, end: Point3D) -> float:
    first = (control[0] - start[0], control[1] - start[1], control[2] - start[2])
    second = (end[0] - control[0], end[1] - control[1], end[2] - control[2])

    def speed(t: float) -> float:
        x = 2 * ((1 - t) * first[0] + t * second[0])
        y = 2 * ((1 - t) * first[1] + t * second[1])
        z = 2 * ((1 - t) * first[2] + t * second[2])
        return math.sqrt(x * x + y * y + z * z)

    def simpson(a: float, b: float, fa: float, fm: float, fb: float) -> float:
        return (b - a) * (fa + 4 * fm + fb) / 6

    def integrate(a, b, fa, fm, fb, whole, tolerance, depth):
        middle = (a + b) / 2
        left_middle = (a + middle) / 2
        right_middle = (middle + b) / 2
        left_mid_value = speed(left_middle)
        right_mid_value = speed(right_middle)
        left = simpson(a, middle, fa, left_mid_value, fm)
        right = simpson(middle, b, fm, right_mid_value, fb)
        difference = left + right - whole
        if depth <= 0 or abs(difference) <= 15 * tolerance:
            return left + right + difference / 15
        return integrate(a, middle, fa, left_mid_value, fm, left, tolerance / 2, depth - 1) + integrate(middle, b, fm, right_mid_value, fb, right, tolerance / 2, depth - 1)

    fa, fm, fb = speed(0.0), speed(0.5), speed(1.0)
    whole = simpson(0.0, 1.0, fa, fm, fb)
    return integrate(0.0, 1.0, fa, fm, fb, whole, max(1e-9, whole * 1e-10), 18)


def _hfss_script(wires: list[dict]) -> str:
    lines = ["# Run from Ansys Electronics Desktop: Tools > Run Script", "import ScriptEnv", 'ScriptEnv.Initialize("Ansoft.ElectronicsDesktop")', "oDesktop.RestoreWindow()", "oProject = oDesktop.GetActiveProject()", 'oDesign = oProject.GetActiveDesign() if oProject else None', 'oEditor = oDesign.SetActiveEditor("3D Modeler") if oDesign else None', 'assert oEditor is not None, "Open an HFSS 3D design before running this script."', ""]
    for wire in wires:
        point_rows = [f'["NAME:PLPoint","X:=","{x:.9f}mil","Y:=","{y:.9f}mil","Z:=","{z:.9f}mil"]' for x, y, z in wire["points_mil"]]
        points = ",".join(point_rows)
        segments = ",".join(f'["NAME:PLSegment","SegmentType:=","Line","StartIndex:=",{index},"NoOfPoints:=",2]' for index in range(len(wire["points_mil"]) - 1))
        lines.extend(["oEditor.CreatePolyline(", '  ["NAME:PolylineParameters","IsPolylineCovered:=",True,"IsPolylineClosed:=",False,', f'   ["NAME:PolylinePoints",{points}],', f'   ["NAME:PolylineSegments",{segments}],', '   ["NAME:PolylineXSection","XSectionType:=","Circle","XSectionOrient:=","Auto",', f'    "XSectionWidth:=","{wire["diameter_um"]:.6f}um","XSectionTopWidth:=","0um",', '    "XSectionHeight:=","0um","XSectionNumSegments:=","12","XSectionBendType:=","Curved"]],', f'  ["NAME:Attributes","Name:=","BondWire_{wire["index"]}","Flags:=","","Color:=","(255 180 0)",', '   "Transparency:=",0,"PartCoordinateSystem:=","Global","UDMId:=","",', '   "MaterialValue:=","\"gold\"","SurfaceMaterialValue:=","\"\"",', '   "SolveInside:=",False,"ShellElement:=",False,"ShellElementThickness:=","0mm",', '   "IsMaterialEditable:=",True,"UseMaterialAppearance:=",False,"IsLightweight:=",False])', ""])
    return "\n".join(lines)


def export_simulation_package(directory: str | Path, bonds: list[Bond], endpoints: Callable[[Bond], tuple[Point3D, Point3D]], labels: Callable[[Bond, str], str]) -> list[Path]:
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    library = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = library.new_cell("BONDWIRE_3D_PROJECTION")
    wires: list[dict] = []
    for index, bond in enumerate(bonds, 1):
        start, end = endpoints(bond)
        control = bond_control_point(bond, start, end)
        points = sample_quadratic(start, control, end)
        diameter_um = max(bond.wire_diameter_um, 0.1)
        cell.add(gdstk.FlexPath([(x * UM_PER_MIL, y * UM_PER_MIL) for x, y, _ in points], diameter_um, layer=200, datatype=index))
        wires.append({"index": index, "endpoint_a": labels(bond, "chip"), "endpoint_b": labels(bond, "board"), "start_mil": start, "control_mil": control, "end_mil": end, "diameter_um": diameter_um, "length_mil": quadratic_length(start, control, end), "points_mil": points})
    gds_path = output / "layout.gds"
    library.write_gds(str(gds_path))
    csv_path = output / "bondwires_3d.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["wire", "point", "x_mil", "y_mil", "z_mil", "x_um", "y_um", "z_um", "diameter_um", "length_mil"])
        for wire in wires:
            for point_index, (x, y, z) in enumerate(wire["points_mil"]):
                writer.writerow([wire["index"], point_index, f"{x:.9f}", f"{y:.9f}", f"{z:.9f}", f"{x * UM_PER_MIL:.9f}", f"{y * UM_PER_MIL:.9f}", f"{z * UM_PER_MIL:.9f}", f"{wire['diameter_um']:.6f}", f"{wire['length_mil']:.9f}"])
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps({"units": "mil", "wires": wires}, indent=2), encoding="utf-8")
    hfss_path = output / "hfss_import.py"
    hfss_path.write_text(_hfss_script(wires), encoding="utf-8")
    readme_path = output / "README.txt"
    readme_path.write_text("layout.gds contains the 2D bondwire projection for ADS/HFSS layout import.\nGDSII is a 2D format and cannot store Z coordinates.\nbondwires_3d.csv and manifest.json contain the full XYZ curve and physical length.\nRun hfss_import.py inside an open HFSS 3D design to create circular gold polylines.\nFor ADS/EMPro, import layout.gds and use bondwires_3d.csv as the 3D bondwire point list.\n", encoding="utf-8")
    return [gds_path, csv_path, manifest_path, hfss_path, readme_path]
