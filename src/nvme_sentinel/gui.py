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
    background-color: #0b0908;
    background-image: radial-gradient(circle at 18% 15%, rgba(251, 146, 60, 0.15), transparent 48%),
                      radial-gradient(circle at 82% 85%, rgba(56, 189, 248, 0.09), transparent 46%);
    color: #fff7ed;
}
headerbar, AdwHeaderBar {
    background: rgba(18, 14, 12, 0.92);
    border-bottom: 1px solid rgba(251, 146, 60, 0.25);
    color: #fff7ed;
}
.nv-card {
    background: rgba(20, 16, 14, 0.94);
    border: 1px solid rgba(251, 146, 60, 0.22);
    border-radius: 16px;
    padding: 15px 18px;
}
.nv-hero {
    background: rgba(24, 19, 16, 0.95);
    border: 1px solid rgba(253, 186, 116, 0.28);
    border-radius: 15px;
    padding: 14px 16px;
}
.hk { font-size: 10.5px; font-weight: 700; color: #fb923c; letter-spacing: 0.7px; }
.hv { font-size: 24px; font-weight: 800; color: #f8fafc; }
.hs { font-size: 11.5px; color: #a8a29e; }
.st { font-size: 14px; font-weight: 700; color: #ffedd5; }
.ss { font-size: 11.5px; color: #a8a29e; }
.row { padding: 6px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
"""


class IopsWaveformCanvas(Gtk.DrawingArea):
    """Live Cairo Write-IOPS (Copper) + Read-MB/s (Cyan) storage chart."""

    def __init__(self) -> None:
        super().__init__()
        self.set_size_request(-1, 175)
        self.set_hexpand(True)
        self._r: deque[float] = deque(maxlen=50)
        self._w: deque[float] = deque(maxlen=50)
        self.set_draw_func(self._draw)

    def push(self, r_iops: float, w_iops: float) -> None:
        self._r.append(r_iops)
        self._w.append(w_iops)
        self.queue_draw()

    def _draw(self, _a, cr: cairo.Context, w: int, h: int) -> None:
        pad_l, pad_r, pad_t, pad_b = 46.0, 14.0, 14.0, 24.0
        cw = max(20.0, w - pad_l - pad_r)
        ch = max(20.0, h - pad_t - pad_b)
        cr.set_source_rgba(0.05, 0.04, 0.04, 0.90)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        peak = max(100.0, max(max(self._r, default=0.0), max(self._w, default=0.0)) * 1.2)
        for f in (0.0, 0.5, 1.0):
            y = pad_t + ch * (1.0 - f)
            cr.set_source_rgba(0.98, 0.57, 0.24, 0.14)
            cr.set_line_width(1.0)
            cr.move_to(pad_l, y); cr.line_to(w - pad_r, y); cr.stroke()
            cr.set_source_rgba(0.75, 0.70, 0.66, 0.8)
            cr.set_font_size(9.5)
            cr.move_to(4, y + 3)
            cr.show_text(f"{peak * f:.0f}")

        if len(self._w) >= 2:
            n = len(self._w)
            pts = [(pad_l + (i / (n - 1)) * cw, pad_t + ch * (1.0 - min(1.0, v / peak))) for i, v in enumerate(self._w)]
            grad = cairo.LinearGradient(0, pad_t, 0, pad_t + ch)
            grad.add_color_stop_rgba(0.0, 0.98, 0.57, 0.24, 0.38)
            grad.add_color_stop_rgba(1.0, 0.98, 0.57, 0.24, 0.02)
            cr.set_source(grad)
            cr.move_to(pts[0][0], pad_t + ch)
            for x, y in pts:
                cr.line_to(x, y)
            cr.line_to(pts[-1][0], pad_t + ch)
            cr.close_path(); cr.fill()

            cr.set_source_rgba(0.98, 0.57, 0.24, 0.96)
            cr.set_line_width(2.2)
            cr.move_to(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                cr.line_to(x, y)
            cr.stroke()

        if len(self._r) >= 2:
            n = len(self._r)
            cr.set_source_rgba(0.22, 0.74, 0.97, 0.90)
            cr.set_line_width(1.8)
            for i, v in enumerate(self._r):
                x = pad_l + (i / (n - 1)) * cw
                y = pad_t + ch * (1.0 - min(1.0, v / peak))
                cr.move_to(x, y) if i == 0 else cr.line_to(x, y)
            cr.stroke()


class NvmeWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="NVMe Sentinel", default_width=1080, default_height=740)
        self._busy = False
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)
        root.append(Adw.HeaderBar(title_widget=Adw.WindowTitle(title="NVMe Sentinel", subtitle="PCIe Link, Controller Thermal, APST Power-State & IOPS Telemetry")))

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=14, margin_bottom=16, margin_start=18, margin_end=18)
        root.append(body)

        hero = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
        c1, self.h_temp, self.h_temp_s = self._hero("CONTROLLER TEMP", "-- C", "Composite hwmon")
        c2, self.h_link, self.h_link_s = self._hero("PCIE LINK & PM", "--", "Runtime PM")
        c3, self.h_apst, self.h_apst_s = self._hero("APST SLEEP BUDGET", "-- us", "PS4 Deep Sleep")
        c4, self.h_io, self.h_io_s = self._hero("LIVE THROUGHPUT", "0 MB/s", "0 Read / 0 Write IOPS")
        for i, c in enumerate((c1, c2, c3, c4)):
            hero.attach(c, i, 0, 1, 1)
        body.append(hero)

        mid = Gtk.Grid(column_spacing=14, row_spacing=14, column_homogeneous=True)
        left = self._card("Live Block Queue IOPS Waveform", "Copper: Write IOPS • Cyan: Read IOPS over /sys/block/nvme0n1/stat")
        self.chart = IopsWaveformCanvas()
        left.append(self.chart)
        self.temp_bar = Gtk.ProgressBar(margin_top=6)
        left.append(self.temp_bar)
        self.drive_lbl = Gtk.Label(label="Drive: scanning...", xalign=0.0)
        self.drive_lbl.add_css_class("ss")
        left.append(self.drive_lbl)

        right = self._card("NVMe Hardware & Multi-Queue Spec", "Real sysfs kernel parameters & runtime attributes")
        self.kv = {}
        for k, title in [
            ("model", "SSD Model"),
            ("firmware", "Controller Firmware"),
            ("scheduler", "Block Scheduler"),
            ("read_ahead", "Read-Ahead Window"),
            ("rq_affinity", "CPU IRQ Queue Affinity"),
            ("nr_requests", "Queue Depth (nr_requests)"),
            ("inflight", "Active In-Flight I/O"),
        ]:
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            r.add_css_class("row")
            kl = Gtk.Label(label=title, xalign=0.0, hexpand=True)
            kl.add_css_class("ss")
            vl = Gtk.Label(label="—", xalign=1.0)
            r.append(kl); r.append(vl)
            right.append(r)
            self.kv[k] = vl

        mid.attach(left, 0, 0, 3, 1)
        mid.attach(right, 3, 0, 2, 1)
        body.append(mid)

        GLib.timeout_add(1600, self._tick)
        self._refresh()

    def _hero(self, k: str, v: str, s: str):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        b.add_css_class("nv-hero")
        kl = Gtk.Label(label=k, xalign=0.0); kl.add_css_class("hk")
        vl = Gtk.Label(label=v, xalign=0.0); vl.add_css_class("hv")
        sl = Gtk.Label(label=s, xalign=0.0, ellipsize=3); sl.add_css_class("hs")
        b.append(kl); b.append(vl); b.append(sl)
        return b, vl, sl

    def _card(self, t: str, s: str) -> Gtk.Box:
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        b.add_css_class("nv-card")
        tl = Gtk.Label(label=t, xalign=0.0); tl.add_css_class("st")
        sl = Gtk.Label(label=s, xalign=0.0); sl.add_css_class("ss")
        b.append(tl); b.append(sl)
        return b

    def _tick(self) -> bool:
        self._refresh()
        return GLib.SOURCE_CONTINUE

    def _refresh(self) -> None:
        if self._busy:
            return
        self._busy = True

        def _worker():
            try:
                data = sample_nvme(130)
            except Exception:
                data = None

            def _apply():
                self._busy = False
                if not data:
                    return GLib.SOURCE_REMOVE
                tc = int(data.get("temp_c", 0) or 0)
                apst = int(data.get("apst_max_latency_us", -1))
                io = data.get("io", {})
                q = data.get("queue", {})

                self.h_temp.set_label(f"{tc}°C" if tc > 0 else "—°C")
                self.h_temp_s.set_label(data.get("apst_grade", "OK").replace("_", " ").title())
                self.h_link.set_label(data.get("pcie_link", "—"))
                self.h_link_s.set_label(f"Runtime PM: {data.get('pm_status', '—')}")
                self.h_apst.set_label(f"{apst} µs" if apst >= 0 else "Kernel Default")
                self.h_apst_s.set_label("PS4 Power Transition Ready" if apst >= 5500 else "Default Transition Budget")
                tot_mb = float(io.get("read_mbs", 0.0)) + float(io.get("write_mbs", 0.0))
                self.h_io.set_label(f"{tot_mb:.2f} MB/s")
                self.h_io_s.set_label(f"R {io.get('read_iops', 0):.0f} / W {io.get('write_iops', 0):.0f} IOPS")

                self.chart.push(float(io.get("read_iops", 0.0)), float(io.get("write_iops", 0.0)))
                self.temp_bar.set_fraction(min(1.0, max(0.05, tc / 85.0)) if tc > 0 else 0.1)
                self.drive_lbl.set_label(f"{data.get('model', 'NVMe')} • Composite {tc}°C • R {io.get('read_mbs', 0.0):.2f} / W {io.get('write_mbs', 0.0):.2f} MB/s")

                self.kv["model"].set_label(str(data.get("model", "—")))
                self.kv["firmware"].set_label(str(data.get("firmware", "—")))
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
        p = Gtk.CssProvider(); p.load_from_data(NVME_CSS)
        d = Gdk.Display.get_default()
        if d:
            Gtk.StyleContext.add_provider_for_display(d, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = self.props.active_window or NvmeWindow(self)
        win.present()


def main() -> int:
    return NvmeApp().run(None)


if __name__ == "__main__":
    raise SystemExit(main())
