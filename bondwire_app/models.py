from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BoardPad:
    number: str
    x_mil: float
    y_mil: float
    width_mil: float
    height_mil: float
    rotation_deg: float = 0.0
    shape: str = "round"
    layer: int = 1
    solder_expansion_mil: float = 0.0
    corner_radius_percent: float = 50.0


@dataclass
class BoardData:
    path: str
    footprint_name: str
    pads: list[BoardPad] = field(default_factory=list)
    metal_layers: list[str] = field(default_factory=list)
    native_primitive_count: int = 0
    preview_svg: bytes = b""
    preview_bbox_mil: tuple[tuple[float, float], tuple[float, float]] | None = None
    first_metal_layer: str = ""
    first_metal_svg: bytes = b""
    first_metal_bbox_mil: tuple[tuple[float, float], tuple[float, float]] | None = None


@dataclass
class ChipPad:
    name: str
    x_um: float
    y_um: float
    polygon_um: list[tuple[float, float]]


@dataclass
class ChipData:
    path: str
    cell_name: str
    bbox_um: tuple[tuple[float, float], tuple[float, float]]
    pads: list[ChipPad] = field(default_factory=list)
    overview_polygons_um: list[list[tuple[float, float]]] = field(default_factory=list)
    preview_png: bytes = b""
    cb_layer: int = 76
    cb_datatype: int = 0
    ap_layer: int = 126
    ap_texttype: int = 0
    search_depth: int = 10


@dataclass
class Bond:
    chip_pad: str = ""
    board_pad: str = ""
    chip_endpoint_type: str = "pad"
    board_endpoint_type: str = "pad"
    chip_free_x_mil: float = 0.0
    chip_free_y_mil: float = 0.0
    chip_free_z_mil: float = 0.0
    board_free_x_mil: float = 0.0
    board_free_y_mil: float = 0.0
    board_free_z_mil: float = 0.0
    chip_offset_x_mil: float = 0.0
    chip_offset_y_mil: float = 0.0
    board_offset_x_mil: float = 0.0
    board_offset_y_mil: float = 0.0
    control_x_mil: float | None = None
    control_y_mil: float | None = None
    control_z_mil: float | None = None
    wire_diameter_um: float = 25.0


@dataclass
class ProjectData:
    pcb_path: str = ""
    gds_path: str = ""
    cb_layer: int = 76
    cb_datatype: int = 0
    ap_layer: int = 126
    ap_texttype: int = 0
    search_depth: int = 10
    chip_x_mil: float = 0.0
    chip_y_mil: float = 0.0
    chip_rotation_deg: float = 0.0
    pcb_rotation_deg: float = 0.0
    pcb_surface_z_mil: float = 0.0
    chip_surface_z_mil: float = 5.0
    bondwire_color: str = "#ff2d8d"
    bondwire_width_mil: float = 0.18
    pdf_include_chip_pad_labels: bool = True
    bonds: list[Bond] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectData":
        known = {field_name for field_name in cls.__dataclass_fields__}
        values = {key: value for key, value in data.items() if key in known}
        values["bonds"] = [Bond(**item) for item in data.get("bonds", [])]
        return cls(**values)

    def resolve_paths(self, project_path: str | Path) -> None:
        base = Path(project_path).resolve().parent
        for attr in ("pcb_path", "gds_path"):
            value = getattr(self, attr)
            if value and not Path(value).is_absolute():
                setattr(self, attr, str((base / value).resolve()))

    def make_paths_relative(self, project_path: str | Path) -> dict[str, Any]:
        data = self.to_dict()
        base = Path(project_path).resolve().parent
        for attr in ("pcb_path", "gds_path"):
            value = data[attr]
            if value:
                try:
                    data[attr] = str(Path(value).resolve().relative_to(base))
                except ValueError:
                    pass
        return data
