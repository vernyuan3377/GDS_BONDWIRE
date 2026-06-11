from bondwire_app.models import Bond, ProjectData


def test_project_round_trip():
    project = ProjectData(
        pcb_path="a.PcbLib",
        gds_path="b.gds",
        chip_x_mil=1.25,
        chip_rotation_deg=90,
        pcb_rotation_deg=45,
        pcb_surface_z_mil=1.5,
        chip_surface_z_mil=8.0,
        bondwire_color="#00aa55",
        bondwire_width_mil=0.42,
        pdf_include_chip_pad_labels=False,
        bonds=[
            Bond(
                "VDD",
                "1",
                chip_offset_x_mil=0.4,
                chip_offset_y_mil=-0.2,
                board_offset_x_mil=0.3,
                board_offset_y_mil=0.1,
                control_x_mil=12.0,
                control_y_mil=15.0,
                control_z_mil=9.0,
                wire_diameter_um=18.0,
            ),
            Bond(
                chip_endpoint_type="free",
                board_endpoint_type="free",
                chip_free_x_mil=12.0,
                chip_free_y_mil=-4.0,
                chip_free_z_mil=7.0,
                board_free_x_mil=20.0,
                board_free_y_mil=8.0,
                board_free_z_mil=1.0,
            ),
        ],
    )
    loaded = ProjectData.from_dict(project.to_dict())
    assert loaded == project
