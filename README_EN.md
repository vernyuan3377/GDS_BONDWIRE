# GDS BondWire Planner

English | [简体中文](README.md)

A Python/PyQt5 desktop application for semiconductor package bond-wire planning. It reads Altium
Designer `PcbLib` footprints and Virtuoso-exported GDSII layouts, identifies chip and PCB pads,
edits BondWire connections, and exports PDF drawings for bonding vendors.

## Features

- Read binary Altium `PcbLib` files and display native footprint graphics, the first metal layer,
  and pad numbers.
- Read GDSII files and identify chip pads and names using configurable `CB Drawing` and `AP Pin`
  layers.
- Adjust chip position, chip rotation, and PCB footprint rotation.
- Draw manual pads in a separate PCB PAD generator/editor window with arbitrary numbers,
  positions, sizes, rotations, shapes, and colors.
- Batch generation and multi-pad editing support optional signed `delta PAD`, `delta X`, and
  `delta Y` steps in mil or mm.
- Move manual pads directly on the canvas and align or distribute them left/right/top/bottom and
  horizontally/vertically using automatic or fixed spacing.
- Use global `Ctrl+Z` to undo pad and BondWire edits, chip/PCB transforms, 3D parameters, and chip
  visibility, even while the PAD editor or 3D window has focus.
- Keep chip pad labels upright while the chip rotates.
- Hide or show the chip geometry, pads, and labels from the toolbar without removing BondWire data.
- Create BondWires by clicking chip pads, external labels, or PCB pads.
- Double-click non-pad areas to create free connection endpoints.
- Drag BondWire endpoints to fine-tune landing positions.
- Configure BondWire color, 2D display width, and 3D wire diameter.
- Display the PCB first metal layer, chip pads, and BondWires in 3D.
- Drag the wire midpoint in 3D to adjust XY position, loop height, or target length.
- Calculate true wire length using adaptive integration of the 3D quadratic Bezier curve.
- Save and open `.bondwire.json` projects.
- Export landscape A3 PDF drawings with optional chip pad labels.
- Export an AD26 footprint-reference DelphiScript with an embedded pad coordinate table.

## Installation

Python 3.11 is recommended:

```powershell
python -m pip install -r requirements.txt
```

## Running

```powershell
python run.py
```

You can also double-click `start.bat`. The application starts with an empty workspace; use the
toolbar to open a PcbLib, GDS, or project file.

Command-line loading:

```powershell
python run.py --pcb your.PcbLib --gds your.gds
python run.py --project example.bondwire.json
python run.py --pcb your.PcbLib --gds your.gds --export-pdf drawing.pdf
```

## Basic Workflow

1. Open a `PcbLib` file and a GDS file.
2. Verify the GDS layer mapping. Defaults are `CB Drawing = 76/0`, `AP Pin = 126/0`, and search
   depth `10`.
3. Adjust chip placement, chip rotation, and PCB footprint rotation.
4. For a custom reference footprint, open the separate PAD editor, set the count, and optionally
   enable signed `delta PAD`, `delta X`, and `delta Y` steps. A negative `delta PAD` decrements IDs.
5. Use Edit Selected PAD to modify, drag, align, or distribute manual pads. Switching to BondWire
   mode preserves existing pad-to-wire relationships.
6. Switch to BondWire drawing mode and click the chip and PCB endpoints.
7. Drag wire endpoints to fine-tune landing positions.
8. Open the 3D view and adjust the wire midpoint, loop height, or target length.
9. Save the project and export the PDF drawing. Export the AD26 footprint-reference script when
   needed.

## Recognition Notes

GDSII usually stores numeric layer/datatype values instead of Virtuoso layer names. The application
therefore allows manual configuration of the `CB Drawing layer/datatype` and `AP Pin
layer/texttype`. Bondable pad geometry is read from CB Drawing, while pad names are matched from AP
Pin text.

The current version reads the first footprint in a `PcbLib` file and is intended for single-footprint
libraries. Before sending drawings to a bonding vendor, manually verify pad names, orientation,
rotation, and every BondWire connection.

## Tests

```powershell
python -m pytest -q
```

## Build a Portable Windows Application

Run in Windows PowerShell:

```powershell
.\build_windows.ps1
```

The output is created in `dist\GDS_BondWire`. Copy the entire folder to another 64-bit Windows
computer and run `GDS_BondWire.exe`; Python does not need to be installed.

To build a single executable instead:

```powershell
.\build_windows.ps1 -OneFile
```

The single-file output is `dist\GDS_BondWire.exe`, but it usually starts more slowly than the
folder build.
