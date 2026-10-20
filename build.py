#!/usr/bin/env python3
"""Render the gythialy profile README as a blueprint sheet.

Everything is drawn locally into committed SVG assets; the page depends on no
third-party badge service. Data comes from the GitHub API (REST + GraphQL) and
the personal blog feed, and is cached so a failed fetch never blanks the page.

Usage:
    python build.py             # regenerate assets/ + README.md
    python build.py --preview   # ... and write preview/page-{light,dark}.html
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
CACHE = ROOT / "data" / "cache.json"

USER = "gythialy"
FEED_URL = "https://gythialy.github.io/atom.xml"
BLOG_URL = "https://gythialy.github.io/"

# --- edit me -----------------------------------------------------------------
NAME_OVERRIDE = ""  # empty = use the GitHub display name
TAGLINE = "SOFTWARE ARCHITECT · CROSS-COMPILERS · IEC 60870-5-104 · HOMELAB INFRA"
STACK = [
    "JAVA",
    "KOTLIN",
    "ANDROID",
    ".NET",
    "GO",
    "NODE.JS",
    "DOCKER",
    "KUBERNETES",
    "TRAEFIK",
    "GIT",
    "JETBRAINS",
    "CLOUDFLARE",
]
POSTS = 5  # rows in "recent writes"
REPOS = 4  # rows in "selected work"
# -----------------------------------------------------------------------------

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"
BT = "\x60"

PALETTES = {
    "dark": {
        "bg": "#071726",
        "minor": "#0d2c44",
        "major": "#14405e",
        "frame": "#2c6d92",
        "inner": "#1a4c69",
        "ink": "#e6f6ff",
        "accent": "#57d9ff",
        "line": "#1f5875",
        "label": "#7cc0de",
        "faint": "#4c93b9",
        "panel": "#0a2233",
        "panelLine": "#1c5878",
        "body": "#d7ecf7",
        "dim": "#a9d6ee",
        "tick": "#2a5f7d",
    },
    "light": {
        "bg": "#f7f4ea",
        "minor": "#e7e0ce",
        "major": "#d8cfb8",
        "frame": "#7b96a6",
        "inner": "#b9c9d2",
        "ink": "#12293a",
        "accent": "#0b7ea1",
        "line": "#c3d3da",
        "label": "#4b7185",
        "faint": "#8aa1ad",
        "panel": "#eef4f7",
        "panelLine": "#c9d8e0",
        "body": "#1d3648",
        "dim": "#3f6175",
        "tick": "#b3c4cd",
    },
}

CHAR_W = {
    " ": 0.278,
    ".": 0.278,
    "#": 0.556,
    "·": 0.278,
    "/": 0.278,
    ":": 0.278,
    "G": 0.778,
    "O": 0.778,
    "R": 0.722,
    "E": 0.667,
    "N": 0.722,
    "Y": 0.667,
    "T": 0.611,
    "H": 0.722,
    "I": 0.278,
    "A": 0.667,
    "L": 0.556,
    "S": 0.667,
}


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def measure(text: str, size: float, tracking: float = 0.0) -> float:
    total = sum(CHAR_W.get(c, 0.72 if c.isupper() else 0.56) * size for c in text)
    return total + tracking * max(0, len(text) - 1)


def txt(
    x, y, s, size=13, fill="#000", fam=SANS, weight=None, anchor=None, ls=None, op=None, style=None
) -> str:
    bits = [
        f'x="{x:.1f}"',
        f'y="{y:.1f}"',
        f'font-family="{fam}"',
        f'font-size="{size}"',
        f'fill="{fill}"',
    ]
    if weight:
        bits.append(f'font-weight="{weight}"')
    if anchor:
        bits.append(f'text-anchor="{anchor}"')
    if ls:
        bits.append(f'letter-spacing="{ls}"')
    if op is not None:
        bits.append(f'opacity="{op}"')
    if style:
        bits.append(f'font-style="{style}"')
    return f"<text {' '.join(bits)}>{esc(s)}</text>"


def rect(x, y, w, h, fill="none", stroke=None, sw=1, rx=0, op=None) -> str:
    bits = [
        f'x="{x:.1f}"',
        f'y="{y:.1f}"',
        f'width="{w:.1f}"',
        f'height="{h:.1f}"',
        f'fill="{fill}"',
    ]
    if stroke:
        bits += [f'stroke="{stroke}"', f'stroke-width="{sw}"']
    if rx:
        bits.append(f'rx="{rx}"')
    if op is not None:
        bits.append(f'opacity="{op}"')
    return f"<rect {' '.join(bits)}/>"


def line(x1, y1, x2, y2, stroke, sw=1, dash=None, op=None) -> str:
    bits = [
        f'x1="{x1:.1f}"',
        f'y1="{y1:.1f}"',
        f'x2="{x2:.1f}"',
        f'y2="{y2:.1f}"',
        f'stroke="{stroke}"',
        f'stroke-width="{sw}"',
    ]
    if dash:
        bits.append(f'stroke-dasharray="{dash}"')
    if op is not None:
        bits.append(f'opacity="{op}"')
    return f"<line {' '.join(bits)}/>"


def svg(width: int, height: int, body: list, defs: str = "") -> str:
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">'
    )
    return head + (f"<defs>{defs}</defs>" if defs else "") + "".join(body) + "</svg>\n"


def clip(text: str, limit: int = 92) -> str:
    flat = " ".join(str(text).split())
    if len(flat) <= limit:
        return flat
    cut = flat[: limit - 1].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "…"


def nice_cap(value: int) -> int:
    if value <= 0:
        return 10
    target = value * 1.05
    exp = 10 ** math.floor(math.log10(target))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if exp * m >= target:
            return round(exp * m)
    return int(exp * 10)


# --- data --------------------------------------------------------------------


class FetchError(RuntimeError):
    pass


def token():
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    gh = shutil.which("gh")
    if gh:
        try:
            out = subprocess.run(
                [gh, "auth", "token"], check=False, capture_output=True, text=True, timeout=10
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except OSError:
            pass
    return None


def request(url: str, tok, payload=None) -> dict:
    data = json.dumps(payload).encode() if payload else None
    headers = {"User-Agent": "gythialy-profile-sheet", "Accept": "application/vnd.github+json"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        raise FetchError(f"{url}: {exc}") from exc


def fetch_profile(tok):
    return request(f"https://api.github.com/users/{USER}", tok)


def fetch_repos(tok):
    return request(f"https://api.github.com/users/{USER}/repos?per_page=100&sort=pushed", tok)


def fetch_contributions(tok):
    if not tok:
        return None
    query = """
    query($login: String!, $from: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from) { contributionCalendar { totalContributions } }
      }
    }"""
    since = (datetime.now(UTC) - timedelta(days=365)).isoformat()
    body = request(
        "https://api.github.com/graphql",
        tok,
        {"query": query, "variables": {"login": USER, "from": since}},
    )
    try:
        return int(
            body["data"]["user"]["contributionsCollection"]["contributionCalendar"][
                "totalContributions"
            ]
        )
    except (KeyError, TypeError):
        return None


def fetch_posts():
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "gythialy-profile-sheet"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            root = ET.fromstring(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ET.ParseError) as exc:
        raise FetchError(str(exc)) from exc
    ns = {"a": "http://www.w3.org/2005/Atom"}
    posts = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link = entry.find("a:link", ns)
        published = (entry.findtext("a:published", default="", namespaces=ns) or "")[:10]
        if title and link is not None:
            posts.append({"date": published, "title": title, "url": link.attrib.get("href", "")})
    if not posts:
        raise FetchError("feed contained no entries")
    return posts


def load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_cache(data: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")


def collect() -> dict:
    tok = token()
    cache = load_cache()
    out = {}
    steps = {
        "profile": lambda: fetch_profile(tok),
        "repos": lambda: fetch_repos(tok),
        "contributions": lambda: fetch_contributions(tok),
        "posts": lambda: fetch_posts(),
    }
    for key, fn in steps.items():
        try:
            value = fn()
            if value is None:
                raise FetchError("empty result")
            out[key] = value
        except FetchError as exc:
            if key in cache:
                print(f"::warning::using cached {key} ({exc})", file=sys.stderr)
                out[key] = cache[key]
            else:
                print(f"::warning::no data for {key} ({exc})", file=sys.stderr)
                out[key] = None
    save_cache({k: v for k, v in out.items() if v is not None})

    profile = out.get("profile") or {}
    repos = out.get("repos") or []
    # featured: repos we own and still maintain (no forks, no archived copies)
    owned = [r for r in repos if not r.get("fork") and not r.get("archived")]
    ranked = sorted(owned, key=lambda r: (-r.get("stargazers_count", 0), r.get("name", "")))
    created = profile.get("created_at", "")
    years = 0
    if created:
        start = datetime.strptime(created[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        years = int((datetime.now(UTC) - start).days // 365.25)
    return {
        "complete": all(out.get(k) is not None for k in ("profile", "repos", "posts")),
        "name": NAME_OVERRIDE or profile.get("name") or profile.get("login") or USER,
        "login": profile.get("login", USER),
        "location": profile.get("location") or "",
        "blog": (profile.get("blog") or BLOG_URL).replace("http://", "https://"),
        "repos": len(repos),
        "stars": sum(r.get("stargazers_count", 0) for r in repos),
        "followers": profile.get("followers", 0),
        "contributions": out.get("contributions"),
        "featured": [
            {
                "name": r.get("name", ""),
                "desc": r.get("description") or "",
                "stars": r.get("stargazers_count", 0),
                "lang": r.get("language") or "",
                "url": r.get("html_url", ""),
            }
            for r in ranked[:REPOS]
        ],
        "posts": (out.get("posts") or [])[:POSTS],
        "since": created[:10],
        "years": years,
    }


# --- drawing -----------------------------------------------------------------


def grid_defs(p: dict) -> str:
    return (
        f'<pattern id="minor" width="20" height="20" patternUnits="userSpaceOnUse">'
        f'<path d="M20 0H0V20" fill="none" stroke="{p["minor"]}" stroke-width="0.7"/></pattern>'
        f'<pattern id="major" width="100" height="100" patternUnits="userSpaceOnUse">'
        f'<rect width="100" height="100" fill="url(#minor)"/>'
        f'<path d="M100 0H0V100" fill="none" stroke="{p["major"]}" stroke-width="1"/></pattern>'
    )


def render_sheet(d: dict, p: dict) -> str:
    W = 880
    cols = 6
    rows = math.ceil(len(STACK) / cols) if STACK else 0
    frame_top, frame_left = 20, 20
    frame_w = W - 2 * frame_left
    y_name, y_rule, y_dim, y_sub = 124, 140, 168, 204
    y_sec1 = y_dim + 76
    y_mod = y_sec1 + 14
    mod_h, mod_gap = 50, 12
    mod_w = (frame_w - 48 - (cols - 1) * mod_gap) / cols
    y_mod_end = y_mod + rows * (mod_h + 12)
    y_sec2 = y_mod_end + 46
    y_lab = y_sec2 + 24
    y_val = y_lab + 32
    y_bar = y_val + 18
    y_fig = y_bar + 40
    H = int(y_fig + 44)

    body = [f'<rect width="{W}" height="{H}" fill="url(#major)"/>']
    body.append(rect(frame_left, frame_top, frame_w, H - 40, stroke=p["frame"]))
    body.append(
        rect(
            frame_left + 10, frame_top + 10, frame_w - 20, H - 60, stroke=p["inner"], sw=0.8, op=0.9
        )
    )
    for cx, cy in (
        (frame_left, frame_top),
        (W - frame_left, frame_top),
        (frame_left, H - frame_top),
        (W - frame_left, H - frame_top),
    ):
        body.append(line(cx - 9, cy, cx + 9, cy, p["faint"], 1))
        body.append(line(cx, cy - 9, cx, cy + 9, p["faint"], 1))

    x0 = frame_left + 24
    x1 = W - frame_left - 24
    body.append(txt(x0, 56, f"PROFILE / {d['name'].upper()}", 9, p["label"], MONO, ls=3))
    body.append(
        txt(
            x1,
            56,
            "SHEET 01 · REV " + datetime.now().strftime("%Y.%m"),
            9,
            p["faint"],
            MONO,
            ls=2,
            anchor="end",
        )
    )

    name = d["name"].upper()
    body.append(txt(x0, y_name, name, 48, p["ink"], SANS, weight=600, ls=9))
    body.append(
        txt(x0 + measure(name, 48, 9) + 12, y_name - 4, "·", 40, p["accent"], SANS, weight=700)
    )
    body.append(line(x0, y_rule, x1, y_rule, p["frame"]))

    dim_len = 256
    body.append(line(x0, y_dim, x0 + dim_len, y_dim, p["label"], 0.9))
    for ex in (x0, x0 + dim_len):
        body.append(line(ex + (8 if ex == x0 else -8), y_dim - 5, ex, y_dim, p["label"], 0.9))
        body.append(line(ex + (8 if ex == x0 else -8), y_dim + 5, ex, y_dim, p["label"], 0.9))
    span = (
        "SINCE " + (d["since"][:4] or "2011") + " → TODAY · " + str(d["years"]) + " YRS IN THE OPEN"
    )
    body.append(txt(x0 + dim_len + 12, y_dim + 4, span, 9, p["label"], MONO, ls=2))
    body.append(txt(x0, y_sub, TAGLINE, 11, p["dim"], MONO, ls=2))

    body.append(txt(x0, y_sec1, "01 — STACK", 9, p["accent"], MONO, ls=3))
    for i, item in enumerate(STACK):
        col, row = i % cols, i // cols
        bx = x0 + col * (mod_w + mod_gap)
        by = y_mod + row * (mod_h + 12)
        body.append(rect(bx, by, mod_w, mod_h, p["panel"], p["panelLine"], 0.9, rx=1))
        body.append(txt(bx + 7, by + 12, f"#{i + 1:02d}", 6.5, p["faint"], MONO))
        body.append(
            txt(bx + mod_w / 2, by + 33, item, 9.5, p["body"], MONO, ls=1.2, anchor="middle")
        )

    body.append(txt(x0, y_sec2, "02 — TELEMETRY", 9, p["accent"], MONO, ls=3))
    meters = [
        ("REPOS", d["repos"]),
        ("STARS", d["stars"]),
        ("FOLLOWERS", d["followers"]),
        ("CONTRIB · 1Y", d["contributions"]),
    ]
    col_w = (x1 - x0) / 4
    bar_w = 108
    for i, (label, value) in enumerate(meters):
        mx = x0 + i * col_w
        body.append(txt(mx, y_lab, label, 8.5, p["label"], MONO, ls=2))
        if value is None:
            body.append(txt(mx, y_val, "—", 26, p["ink"], MONO, weight=600))
            body.append(rect(mx, y_bar, bar_w, 4, p["panel"]))
            continue
        cap = nice_cap(int(value))
        body.append(txt(mx, y_val, f"{int(value):,}", 26, p["ink"], MONO, weight=600))
        for t in range(5):
            body.append(
                line(mx + t * bar_w / 4, y_bar - 8, mx + t * bar_w / 4, y_bar + 6, p["tick"], 0.8)
            )
        body.append(rect(mx, y_bar, bar_w, 4, p["panel"]))
        body.append(rect(mx, y_bar, bar_w * min(1.0, value / cap), 4, p["accent"]))
        body.append(txt(mx, y_bar + 18, "0", 7, p["faint"], MONO))
        body.append(txt(mx + bar_w, y_bar + 18, f"{cap:,}", 7, p["faint"], MONO, anchor="end"))

    body.append(
        txt(
            x0,
            y_fig,
            "FIG. 1 — VALUES LIVE FROM THE GITHUB API · NOT TO SCALE",
            8.5,
            p["faint"],
            MONO,
            ls=1.5,
        )
    )
    return svg(W, H, body, grid_defs(p))


def render_strip(label: str, p: dict) -> str:
    W, H = 880, 44
    body = [rect(4, 10, 3, 12, fill=p["accent"])]
    body.append(txt(16, 22, label, 10, p["label"], MONO, ls=3.2))
    start = 16 + measure(label, 10, 3.2) + 16
    body.append(line(start, 18, W - 4, 18, p["line"], 1))
    x = start
    while x < W - 8:
        body.append(line(x, 14, x, 18, p["tick"], 1))
        x += 44
    return svg(W, H, body)


def render_footer(p: dict) -> str:
    W, H = 880, 44
    cells = [
        ("GYTHIALY / PROFILE", 300),
        ("REV " + datetime.now().strftime("%Y.%m"), 150),
        ("SCALE 1:1", 120),
        ("GENERATED BY GITHUB ACTIONS", 302),
    ]
    body = [rect(4, 6, W - 8, 32, stroke=p["panelLine"], sw=0.9)]
    x = 4
    for label, width in cells:
        if x > 4:
            body.append(line(x, 6, x, 38, p["panelLine"], 0.9))
        body.append(txt(x + 8, 27, label, 8, p["label"], MONO, ls=1.2))
        x += width
    return svg(W, H, body)


# --- page --------------------------------------------------------------------


def picture(name: str, alt: str) -> str:
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">\n'
        f'  <img alt="{esc(alt)}" src="assets/{name}-light.svg" width="100%">\n'
        "</picture>"
    )


def compose_readme(d: dict) -> str:
    lines = ["<!-- generated by build.py — edit build.py, not this file -->"]
    lines += [picture("sheet", d["name"] + " — profile sheet"), ""]
    lines += [picture("strip-writes", "03 — recent writes"), ""]
    lines += ["| DATE | ARTICLE |", "| :--- | :--- |"]
    for post in d["posts"]:
        lines.append(
            "| " + BT + post["date"] + BT + " | [" + post["title"] + "](" + post["url"] + ") |"
        )
    lines += ["", "[All posts →](" + BLOG_URL + ")", ""]
    lines += [picture("strip-work", "04 — selected work"), ""]
    lines += ["| REPO | ABOUT | LANG | ★ |", "| :--- | :--- | :---: | ---: |"]
    for repo in d["featured"]:
        about = clip(repo["desc"]).replace("|", "\\|") or "—"
        lang = BT + repo["lang"] + BT if repo["lang"] else "—"
        lines.append(
            "| ["
            + repo["name"]
            + "]("
            + repo["url"]
            + ") | "
            + about
            + " | "
            + lang
            + " | "
            + str(repo["stars"])
            + " |"
        )
    lines += ["", picture("strip-foot", "05 — sheet title block")]
    return "\n".join(lines).rstrip() + "\n"


def write(path: Path, content: str) -> bool:
    if path.exists() and path.read_text("utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, "utf-8")
    return True


def inline(md: str) -> str:
    out = esc(md)
    out = re.sub(r"\x60([^\x60]+)\x60", r"<code>\1</code>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    return out


def markdown_to_html(md: str, theme: str) -> str:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)
    md = md.replace("-light.svg", "-" + theme + ".svg")
    md = re.sub(r"\n?\s*<source [^>]*>", "", md)
    out = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("<picture>"):
            block = [ln]
            i += 1
            while i < len(lines) and "</picture>" not in lines[i]:
                block.append(lines[i])
                i += 1
            block.append("</picture>")
            i += 1
            out.append("\n".join(block))
            continue
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            aligns = []
            for cell in rows[1]:
                if cell.startswith(":") and cell.endswith(":"):
                    aligns.append("center")
                elif cell.endswith(":"):
                    aligns.append("right")
                else:
                    aligns.append("left")
            html_rows = []
            for idx, row in enumerate(rows):
                if idx == 1:
                    continue
                tag = "th" if idx == 0 else "td"
                cells = "".join(
                    "<"
                    + tag
                    + ' style="text-align:'
                    + (aligns[c] if c < len(aligns) else "left")
                    + '">'
                    + inline(cell)
                    + "</"
                    + tag
                    + ">"
                    for c, cell in enumerate(row)
                )
                html_rows.append("<tr>" + cells + "</tr>")
            out.append("<table>" + "".join(html_rows) + "</table>")
            continue
        if ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append("<li>" + inline(lines[i][2:]) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        if ln.strip():
            out.append("<p>" + inline(ln) + "</p>")
        i += 1
    return "\n".join(out)


def render_preview_html(d: dict, theme: str) -> str:
    body = markdown_to_html(compose_readme(d), theme)
    body = body.replace('="assets/', '="../assets/')
    if theme == "dark":
        bg, fg, border, head, code, link, muted = (
            "#0d1117",
            "#e6edf3",
            "#3d444d",
            "#161b22",
            "#262626",
            "#4493f8",
            "#9198a1",
        )
    else:
        bg, fg, border, head, code, link, muted = (
            "#ffffff",
            "#1f2328",
            "#d1d9e0",
            "#f6f8fa",
            "#eff1f3",
            "#0969da",
            "#59636e",
        )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>README preview (%s)</title>
<style>
  body { margin:0; background:%s; color:%s; font: 16px/1.5 %s; }
  main { max-width: 880px; margin: 0 auto; padding: 32px 16px 96px; }
  img { max-width:100%%; display:block; }
  table { border-collapse: collapse; width:100%%; margin: 0 0 16px; }
  th, td { border: 1px solid %s; padding: 6px 13px; }
  th { background:%s; font-weight:600; text-align:left; }
  code { background:%s; padding: .2em .4em; border-radius: 6px; font-size: 85%%;
         font-family: %s; }
  a { color:%s; text-decoration:none; }
  a:hover { text-decoration:underline; }
  p { color:%s; font-size: 13px; }
</style></head><body><main>
%s
</main></body></html>
""" % (theme, bg, fg, SANS, border, head, code, MONO, link, muted, body)


def main() -> int:
    data = collect()
    if not data["complete"]:
        print(
            "::warning::core data unavailable — keeping the committed page as is", file=sys.stderr
        )
        return 0
    for theme, palette in PALETTES.items():
        write(ASSETS / f"sheet-{theme}.svg", render_sheet(data, palette))
        write(ASSETS / f"strip-writes-{theme}.svg", render_strip("03 — RECENT WRITES", palette))
        write(ASSETS / f"strip-work-{theme}.svg", render_strip("04 — SELECTED WORK", palette))
        write(ASSETS / f"strip-foot-{theme}.svg", render_footer(palette))
    write(ROOT / "README.md", compose_readme(data))
    if "--preview" in sys.argv:
        for theme in PALETTES:
            write(ROOT / "preview" / f"page-{theme}.html", render_preview_html(data, theme))
    print(
        f"sheet ready: {data['repos']} repos · {data['stars']} stars · "
        f"{data['followers']} followers · {data['contributions']} contributions"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
