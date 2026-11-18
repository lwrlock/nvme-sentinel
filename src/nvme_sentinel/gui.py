from __future__ import annotations

import os
import threading
from collections import deque

os.environ.setdefault("GSK_RENDERER", "gl")

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from .monitor import sample_nvme

NVME_CSS = b"""
window, window.background, AdwApplicationWindow {
    background-color: #09090b;
    background-image: radial-gradient(circle at 18% 12%, rgba(251, 146, 60, 0.12), transparent 46%),
                      radial-gradient(circle at 86% 85%, rgba(56, 189, 248, 0.08), transparent 46%);
    color: #fff7ed;
}
headerbar, AdwHeaderBar {
    background: #121216;
    border-bottom: 1px solid rgba(251, 146, 60, 0.25);
    color: #fff7ed;
    min-height: 42px;
}
.nameplate {
    background: #131317;
    border: 1px solid rgba(251, 146, 60, 0.28);
    border-radius: 8px;
    padding: 11px 16px;
}
.nv-panel {
    background: #121216;
    border: 1px solid rgba(251, 146, 60, 0.20);
    border-radius: 8px;
    padding: 13px 15px;
}
.plate-model { font-family: monospace; font-size: 17px; font-weight: 800; color: #ffedd5; }
.plate-meta { font-family: monospace; font-size: 11.5px; color: #fdba74; }
.st { font-size: 13.5px; font-weight: 700; color: #ffedd5; }
.ss { font-size: 11px; color: #a1a1aa; }
.mono { font-family: monospace; font-size: 12px; color: #f4f4f5; }
.row { padding: 6px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
.rate-btn {
    border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 700;
    background: rgba(251, 146, 60, 0.14); border: 1px solid rgba(251, 146, 60, 0.30);
}
.rate-active {
    background: rgba(251, 146, 60, 0.30);
    border: 1px solid #fb923c;
    color: #fff7ed;
}
"""


class ThermalApstCanvas(Gtk.DrawingArea):
    """Draws a vertical NVMe thermal column (0..85 C) beside an APST PS0..PS4 state ladder."""

    def __init__(self) -> None:
        super().__init__()
        self.set_size_request(-1, 290)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self._temp = 30
        self._apst_us = 5500
        self._grade = "DEEP_PS4_OPTIMAL"
        self.set_draw_func(self._draw)

    def update(self, temp_c: int, apst_us: int, grade: str) -> None:
        self._temp = max(0, temp_c)
        self._apst_us = apst_us
        self._grade = grade
        self.queue_draw()

    def _draw(self, _a, cr: cairo.Context, w: int, h: int) -> None:
        cr.set_source_rgba(0.05, 0.05, 0.07, 0.96)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        # Left Half: Vertical Thermometer Tube (0..85 C)
        tx, ty, tw, th = 28.0, 26.0, 28.0, max(80.0, h - 70.0)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.08)
        cr.rectangle(tx, ty, tw, th)
        cr.fill()

        frac = min(1.0, max(0.04, self._temp / 85.0))
        fill_h = th * frac
        rgb = (0.06, 0.72, 0.51) if self._temp < 55 else ((0.98, 0.57, 0.24) if self._temp < 70 else (0.96, 0.25, 0.37))
        cr.set_source_rgba(rgb[0], rgb[1], rgb[2], 0.92)
        cr.rectangle(tx, ty + th - fill_h, tw, fill_h)
        cr.fill()

        # 70 C Thermal Throttle Warning Marker
        warn_y = ty + th * (1.0 - 70.0 / 85.0)
        cr.set_source_rgba(0.96, 0.25, 0.37, 0.85)
        cr.set_line_width(1.4)
        cr.move_to(tx - 6, warn_y)
        cr.line_to(tx + tw + 8, warn_y)
        cr.stroke()
        cr.set_font_size(8.5)
        cr.move_to(tx + tw + 10, warn_y + 3)
        cr.show_text("70C")

        cr.set_source_rgba(0.98, 0.95, 0.90, 0.96)
        cr.set_font_size(14.0)
        cr.move_to(tx - 6, h - 18)
        cr.show_text(f"{self._temp}°C" if self._temp > 0 else "—°C")
        cr.set_source_rgba(0.65, 0.65, 0.70, 0.85)
        cr.set_font_size(9.5)
        cr.move_to(tx - 12, 16)
        cr.show_text("THERMAL")

        # Right Half: APST Power State Ladder (PS0..PS4)
        lx = max(92.0, w * 0.39)
        lw = max(90.0, w - lx - 12.0)
        cr.set_source_rgba(0.98, 0.57, 0.24, 0.92)
        cr.set_font_size(9.5)
        cr.move_to(lx, 16)
        cr.show_text(f"APST BUDGET ({self._apst_us} µs)")

        states = [
            ("PS0 Active", "Full PCIe I/O", 0),
            ("PS1 Light", "~1.5W idle", 500),
            ("PS2 Lower", "~0.5W idle", 1500),
            ("PS3 Sleep", "~50mW non-op", 3500),
            ("PS4 Deep", "<=5mW idle", 5500),
        ]
        step_h = (th - 16.0) / len(states)
        for i, (name, sub, req_us) in enumerate(states):
            sy = 28.0 + i * (step_h + 4.0)
            enabled = (self._apst_us >= req_us) or (self._apst_us == -1)
            if enabled:
                cr.set_source_rgba(0.98, 0.57, 0.24, 0.16 if req_us < 5500 else 0.26)
            else:
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.04)
            cr.rectangle(lx, sy, lw, step_h)
            cr.fill()
            cr.set_source_rgba(0.98, 0.57, 0.24, 0.55 if enabled else 0.14)
            cr.rectangle(lx, sy, lw, step_h)
            cr.stroke()

            cr.set_source_rgba(1.0, 0.96, 0.92, 0.96 if enabled else 0.45)
            cr.set_font_size(10.5)
            cr.move_to(lx + 8, sy + 15)
            cr.show_text(name)
            cr.set_source_rgba(0.75, 0.72, 0.70, 0.85 if enabled else 0.35)
            cr.set_font_size(9.0)
            cr.move_to(lx + 8, sy + 28)
            cr.show_text(sub)


class DualStorageCharts(Gtk.DrawingArea):
    """Upper sub-chart: Read/Write IOPS. Lower sub-chart: Read/Write Throughput (MB/s)."""

    def __init__(self) -> None:
        super().__init__()
        self.set_size_request(-1, 290)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self._ri: deque[float] = deque(maxlen=50)
        self._wi: deque[float] = deque(maxlen=50)
        self._rm: deque[float] = deque(maxlen=50)
        self._wm: deque[float] = deque(maxlen=50)
        self.set_draw_func(self._draw)

    def push(self, r_iops: float, w_iops: float, r_mbs: float, w_mbs: float) -> None:
        self._ri.append(r_iops)
        self._wi.append(w_iops)
        self._rm.append(r_mbs)
        self._wm.append(w_mbs)
        self.queue_draw()

    def _draw_band(self, cr: cairo.Context, x0: float, y0: float, cw: float, ch: float, s1: deque[float], s2: deque[float], min_peak: float, title: str, unit: str) -> None:
        peak = max(min_peak, max(max(s1, default=0.0), max(s2, default=0.0)) * 1.2)
        for f in (0.0, 0.5, 1.0):
            y = y0 + ch * (1.0 - f)
            cr.set_source_rgba(0.98, 0.57, 0.24, 0.14)
            cr.move_to(x0, y); cr.line_to(x0 + cw, y); cr.stroke()
            cr.set_source_rgba(0.74, 0.74, 0.78, 0.80)
            cr.set_font_size(9.0)
            cr.move_to(4, y + 3)
            cr.show_text(f"{peak * f:.1f}{unit}" if min_peak < 10 else f"{peak * f:.0f}{unit}")

        cr.set_source_rgba(0.98, 0.90, 0.80, 0.90)
        cr.set_font_size(10.0)
        cr.move_to(x0 + 6, y0 + 12)
        cr.show_text(title)

        for series, rgb in ((s1, (0.22, 0.74, 0.97)), (s2, (0.98, 0.57, 0.24))):
            if len(series) >= 2:
                cr.set_source_rgba(rgb[0], rgb[1], rgb[2], 0.95)
                cr.set_line_width(2.0)
                n = len(series)
                for i, v in enumerate(series):
                    x = x0 + (i / (n - 1)) * cw
                    y = y0 + ch * (1.0 - min(1.0, v / peak))
                    cr.move_to(x, y) if i == 0 else cr.line_to(x, y)
                cr.stroke()

    def _draw(self, _a, cr: cairo.Context, w: int, h: int) -> None:
        cr.set_source_rgba(0.05, 0.05, 0.07, 0.96)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        pad_l, pad_r, pad_t, gap = 52.0, 12.0, 12.0, 18.0
        cw = max(40.0, w - pad_l - pad_r)
        band_h = max(60.0, (h - pad_t - gap - 14.0) * 0.5)
        self._draw_band(cr, pad_l, pad_t, cw, band_h, self._ri, self._wi, 100.0, "IOPS  (Cyan: Read • Copper: Write)", "")
        self._draw_band(cr, pad_l, pad_t + band_h + gap, cw, band_h, self._rm, self._wm, 5.0, "THROUGHPUT MB/s  (Cyan: Read • Copper: Write)", "")


class NvmeWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="NVMe Sentinel", default_width=1140, default_height=730)
        self._busy = False
        self._sample_ms = 130

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)
        hb = Adw.HeaderBar(title_widget=Adw.WindowTitle(title="NVMe Sentinel", subtitle="Thermal Column • APST Ladder • Multi-Queue Spec"))
        rate_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._rbtns: dict[int, Gtk.Button] = {}
        for ms in (80, 130, 300):
            b = Gtk.Button(label=f"{ms}ms")
            b.add_css_class("rate-btn")
            if ms == self._sample_ms:
                b.add_css_class("rate-active")
            b.connect("clicked", self._set_rate, ms)
            rate_box.append(b)
            self._rbtns[ms] = b
        hb.pack_end(rate_box)
        root.append(hb)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=14, margin_start=16, margin_end=16)
        root.append(body)

        # Top Full-Width Hardware Nameplate Bar (Replaces 4 top hero cards)
        plate = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        plate.add_css_class("nameplate")
        pl_left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self.np_model = Gtk.Label(label="Probing /sys/class/nvme/nvme0...", xalign=0.0); self.np_model.add_css_class("plate-model")
        self.np_meta = Gtk.Label(label="PCIe Link: —  •  Runtime PM: —  •  APST: —", xalign=0.0); self.np_meta.add_css_class("plate-meta")
        pl_left.append(self.np_model); pl_left.append(self.np_meta)
        self.np_io = Gtk.Label(label="0.00 MB/s  •  0 IOPS", xalign=1.0, valign=Gtk.Align.CENTER); self.np_io.add_css_class("plate-model")
        plate.append(pl_left); plate.append(self.np_io)
        body.append(plate)

        # 3-Column Drive Engineering Workbench
        cols = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True, vexpand=True)

        c1 = self._panel("Thermal & APST Ladder", "Controller hwmon & deep sleep policy")
        self.therm_apst = ThermalApstCanvas()
        c1.append(self.therm_apst)

        c2 = self._panel("Block Queue IOPS & Throughput", "Live deltas from /sys/block/nvme0n1/stat")
        self.io_charts = DualStorageCharts()
        c2.append(self.io_charts)
        self.io_foot = Gtk.Label(label="Read: 0.00 MB/s • Write: 0.00 MB/s • In-Flight: 0", xalign=0.0)
        self.io_foot.add_css_class("mono")
        c2.append(self.io_foot)

        c3 = self._panel("Block Queue & Controller Spec", "Kernel sysfs attributes")
        self.kv: dict[str, Gtk.Label] = {}
        for k, title in [
            ("model", "SSD Model"),
            ("firmware", "Firmware Rev"),
            ("pcie", "PCIe Link Width"),
            ("pm", "Runtime PM State"),
            ("apst_grade", "APST Policy Grade"),
            ("scheduler", "Block Scheduler"),
            ("read_ahead", "Read-Ahead Window"),
            ("rq_affinity", "RQ Affinity"),
            ("nr_requests", "Queue Depth"),
            ("inflight", "Active In-Flight"),
        ]:
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            r.add_css_class("row")
            kl = Gtk.Label(label=title, xalign=0.0, hexpand=True); kl.add_css_class("ss")
            vl = Gtk.Label(label="—", xalign=1.0); vl.add_css_class("mono")
            r.append(kl); r.append(vl)
            c3.append(r)
            self.kv[k] = vl

        cols.attach(c1, 0, 0, 3, 1)
        cols.attach(c2, 3, 0, 5, 1)
        cols.attach(c3, 8, 0, 4, 1)
        body.append(cols)

        GLib.timeout_add(140, self._warmup_tick)
        GLib.timeout_add(450, self._warmup_tick)
        GLib.timeout_add(850, self._warmup_tick)
        GLib.timeout_add(1500, self._tick)

    def _set_rate(self, _btn, ms: int) -> None:
        self._sample_ms = ms
        for k, b in self._rbtns.items():
            b.remove_css_class("rate-active")
            if k == ms:
                b.add_css_class("rate-active")
        self._refresh()

    def _panel(self, t: str, s: str) -> Gtk.Box:
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        b.add_css_class("nv-panel")
        tl = Gtk.Label(label=t, xalign=0.0); tl.add_css_class("st")
        sl = Gtk.Label(label=s, xalign=0.0); sl.add_css_class("ss")
        b.append(tl); b.append(sl)
        return b

    def _warmup_tick(self) -> bool:
        self._refresh()
        return GLib.SOURCE_REMOVE

    def _tick(self) -> bool:
        self._refresh()
        return GLib.SOURCE_CONTINUE

    def _refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        ms = self._sample_ms

        def _worker():
            try:
                data = sample_nvme(ms)
            except Exception:
                data = None

            def _apply():
                self._busy = False
                if not data:
                    return GLib.SOURCE_REMOVE

                tc = int(data.get("temp_c", 0) or 0)
                apst = int(data.get("apst_max_latency_us", -1))
                grade = str(data.get("apst_grade", "OK"))
                io = data.get("io", {})
                q = data.get("queue", {})
                r_mbs = float(io.get("read_mbs", 0.0))
                w_mbs = float(io.get("write_mbs", 0.0))
                r_iops = float(io.get("read_iops", 0.0))
                w_iops = float(io.get("write_iops", 0.0))

                self.np_model.set_label(f"{data.get('model', 'NVMe')}  (FW {data.get('firmware', '—')})")
                self.np_meta.set_label(f"Link: {data.get('pcie_link', '—')}  •  PM: {data.get('pm_status', '—')}  •  Temp: {tc}°C  •  APST: {apst} µs")
                self.np_io.set_label(f"{r_mbs + w_mbs:.2f} MB/s  •  {r_iops + w_iops:.0f} IOPS")

                self.therm_apst.update(tc, apst, grade)
                self.io_charts.push(r_iops, w_iops, r_mbs, w_mbs)
                self.io_foot.set_label(f"Read: {r_mbs:.2f} MB/s ({r_iops:.0f} IOPS)  •  Write: {w_mbs:.2f} MB/s ({w_iops:.0f} IOPS)  •  In-Flight: {io.get('inflight', 0)}")

                self.kv["model"].set_label(str(data.get("model", "—")))
                self.kv["firmware"].set_label(str(data.get("firmware", "—")))
                self.kv["pcie"].set_label(str(data.get("pcie_link", "—")))
                self.kv["pm"].set_label(str(data.get("pm_status", "—")))
                self.kv["apst_grade"].set_label(grade.replace("_", " "))
                self.kv["scheduler"].set_label(str(q.get("scheduler", "none")))
                self.kv["read_ahead"].set_label(f"{q.get('read_ahead_kb', 0)} KB")
                self.kv["rq_affinity"].set_label(f"Level {q.get('rq_affinity', 0)}")
                self.kv["nr_requests"].set_label(str(q.get("nr_requests", 0)))
                self.kv["inflight"].set_label(str(io.get("inflight", 0)))
                return GLib.SOURCE_REMOVE

            GLib.idle_add(_apply)

        threading.Thread(target=_worker, daemon=True).start()


class NvmeApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.lwrlock.NvmeSentinel")

    def do_activate(self):
        p = Gtk.CssProvider()
        p.load_from_data(NVME_CSS)
        d = Gdk.Display.get_default()
        if d:
            Gtk.StyleContext.add_provider_for_display(d, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = self.props.active_window or NvmeWindow(self)
        win.present()


def main() -> int:
    return NvmeApp().run(None)


if __name__ == "__main__":
    raise SystemExit(main())
