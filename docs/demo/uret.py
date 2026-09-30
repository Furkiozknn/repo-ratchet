"""Renders the README demo (docs/demo/demo.gif) and the vertical clip (terminal.mp4)
from docs/demo/demo.json, which docs/demo/kaydet.py writes by running the real commands.

Nothing here invents output: every line drawn is a line ratchet printed.
Dev-time only - needs Pillow and ffmpeg; the package itself stays dependency-free.

    python docs/demo/kaydet.py   # runs the commands in a throwaway git repo -> demo.json
    python docs/demo/uret.py gif demo.gif      # 960x540 for the README
    python docs/demo/uret.py mp4 terminal.mp4  # 1080x1920, H.264, silent

Colours: FRK-OS - black #0e0d0b, cream #f1ece2, yellow #ffc21a. Contrast on black (computed): cream 16.5:1,
yellow 12.0:1, dim cream #9a958b 6.5:1, refusal red #ff7a6b 7.6:1 (all >= 4.5:1).
"""
import json, subprocess, sys, textwrap, tempfile, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
BG, FG, YEL, DIM, RED = "#0e0d0b", "#f1ece2", "#ffc21a", "#9a958b", "#ff7a6b"
PICK = [1, 2, 3, 4, 6]  # steps of demo.json shown (skips --version and the report table)


def steps():
    log = json.loads((HERE / "demo.json").read_text(encoding="utf-8"))
    return [log[i] for i in PICK]


def timeline(fps):
    """Yield (lines, cursor_visible) per frame: type the command, then show its output."""
    lines, frames = [], []
    def snap(n, cur=True):
        for _ in range(int(n * fps)):
            frames.append((list(lines), cur))
    snap(1.0, False)
    for cmd, out, rc in steps():
        text = "$ " + cmd
        lines.append(("", ""))
        for k in range(0, len(text) + 1, 3):  # 3 chars per tick
            lines[-1] = (text[:k], "cmd")
            frames.append((list(lines), True))
            frames.extend([(list(lines), True)] * 0)
        lines[-1] = (text, "cmd")
        snap(0.35)
        for ln in out.splitlines():
            lines.append((ln, "err" if ln.startswith("refused") else "out"))
        lines.append(("[exit %d]" % rc, "dim"))
        snap(1.9 if len(out.splitlines()) < 4 else 2.4)
    snap(1.2, False)
    return frames


def render(lines, cursor, w, h, cols, size, title):
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    reg = ImageFont.truetype(str(HERE / "fonts/JetBrainsMono-Regular.ttf"), size)
    bold = ImageFont.truetype(str(HERE / "fonts/JetBrainsMono-Bold.ttf"), size)
    lh = int(size * 1.45)
    pad = int(size * 1.4)
    d.text((pad, pad // 2), title, font=bold, fill=YEL)
    rows = []
    for text, kind in lines:
        wrapped = textwrap.wrap(text, cols, subsequent_indent="  ", drop_whitespace=False,
                                break_long_words=True, break_on_hyphens=False) or [""]
        rows += [(r, kind) for r in wrapped]
    cap = (h - pad * 2 - lh) // lh
    rows = rows[-cap:]
    y = pad + lh
    for r, kind in rows:
        col = {"cmd": FG, "out": FG, "dim": DIM, "err": RED}[kind]
        d.text((pad, y), r, font=bold if kind == "cmd" else reg, fill=YEL if kind == "cmd" and r.startswith("$") else col)
        y += lh
    if cursor and rows:
        cw = d.textlength("M", font=reg)
        last = rows[-1][0]
        d.rectangle([pad + cw * len(last), y - lh + 3, pad + cw * len(last) + cw * 0.6, y - 5], fill=YEL)
    return im


def main():
    kind, out = sys.argv[1], Path(sys.argv[2]).resolve()
    if kind == "gif":
        fps, (w, h, cols, size) = 10, (960, 540, 70, 16)
    else:
        fps, (w, h, cols, size) = 15, (1080, 1920, 60, 27)
    fr = timeline(fps)
    title = "repo-ratchet: a record cannot lie"
    tmp = Path(tempfile.mkdtemp())
    if kind == "gif":
        ims = [render(l, c, w, h, cols, size, title).convert("P", palette=Image.ADAPTIVE, colors=16) for l, c in fr]
        ims[0].save(out, save_all=True, append_images=ims[1:], duration=int(1000 / fps), loop=0, optimize=True)
    else:
        for i, (l, c) in enumerate(fr):
            render(l, c, w, h, cols, size, title).save(tmp / ("f%05d.png" % i))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(tmp / "f%05d.png"),
                        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(out, "%.1f s" % (len(fr) / fps))


main()
