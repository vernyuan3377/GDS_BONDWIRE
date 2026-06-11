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
- Keep chip pad labels upright while the chip rotates.
- Create BondWires by clicking chip pads, external labels, or PCB pads.
- Double-click non-pad areas to create free connection endpoints.
- Drag BondWire endpoints to fine-tune landing positions.
- Configure BondWire color, 2D display width, and 3D wire diameter.
- Display the PCB first metal layer, chip pads, and BondWires in 3D.
- Drag the wire midpoint in 3D to adjust XY position, loop height, or target length.
- Calculate true wire length using adaptive integration of the 3D quadratic Bezier curve.
- Save and open `.bondwire.json` projects.
- Export landscape A3 PDF drawings with optional chip pad labels.

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
4. Switch to BondWire drawing mode and click the chip and PCB endpoints.
5. Drag wire endpoints to fine-tune landing positions.
6. Open the 3D view and adjust the wire midpoint, loop height, or target length.
7. Save the project and export the PDF drawing.

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

## Repository Contents

The default `.gitignore` excludes `DATA`, `vendor`, PDFs, and local `.bondwire.json` project files to
avoid accidentally publishing design data or generated files.
