import time
from pathlib import Path

import plotly.graph_objects as go

from reporting import charts


def test_save_figure_writes_html_when_png_export_times_out(monkeypatch, tmp_path):
    fig = go.Figure()

    monkeypatch.setattr(charts, "ensure_output_dir", lambda: tmp_path)

    def slow_write_image(*args, **kwargs):
        time.sleep(0.2)

    monkeypatch.setattr(go.Figure, "write_image", slow_write_image)

    charts._save_figure(fig, "demo_chart", png_export_timeout=0.01)

    assert (tmp_path / "demo_chart.html").exists()
    assert not (tmp_path / "demo_chart.png").exists()
