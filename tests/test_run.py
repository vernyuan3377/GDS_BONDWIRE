from argparse import Namespace

from run import load_requested_inputs


class FakeWindow:
    def __init__(self):
        self.calls = []

    def open_project(self, path):
        self.calls.append(("project", path))

    def load_pcblib_file(self, path):
        self.calls.append(("pcb", path))

    def load_gds_file(self, path):
        self.calls.append(("gds", path))


def test_startup_without_arguments_does_not_load_default_files():
    window = FakeWindow()
    load_requested_inputs(
        window,
        Namespace(project=None, pcb=None, gds=None, export_pdf=None),
    )
    assert window.calls == []


def test_startup_loads_only_explicit_inputs(tmp_path):
    pcb = tmp_path / "explicit.PcbLib"
    gds = tmp_path / "explicit.gds"
    pcb.write_bytes(b"")
    gds.write_bytes(b"")
    window = FakeWindow()

    load_requested_inputs(
        window,
        Namespace(project=None, pcb=str(pcb), gds=str(gds), export_pdf=None),
    )
    assert window.calls == [("pcb", str(pcb)), ("gds", str(gds))]
