"""Brand spec: named colors, fonts, logos and assets for a brand system, plus website import.

The spec lives in Project.brand_spec_json:
  {"colors": [{"name", "hex"}], "fonts": [{"role", "family"}], "logos": [{"name", "url"}], "assets": [{"name", "url"}]}
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from collections import Counter
from urllib.parse import urljoin, urlparse

import httpx

MAX_COLORS = 12
MAX_FONTS = 10
MAX_FILES = 20
COLOR_ROLES = ["Background", "Main text", "Accent", "Panel background", "Dark panel", "Secondary text"]
FONT_ROLES = ["Body", "Label", "Display", "Heading", "Heading 2"]
FILE_URL_PREFIX = "/storage/brand/"
_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_FONT = re.compile(r"[^A-Za-z0-9 \-]")
_PAGE_LIMIT = 1_500_000
_IMAGE_LIMIT = 2_000_000
_TIMEOUT = 12.0
_GENERIC_FONTS = {"inherit", "initial", "sans-serif", "serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace", "unset", "arial", "helvetica", "times new roman"}

# Starter palettes and fonts per style, written for this studio.
STYLE_PRESETS: dict[str, list[dict]] = {
    "Modern": [
        {"name": "Slate and sky", "colors": ["#F4F6F8", "#0F172A", "#38BDF8", "#E2E8F0", "#1E293B", "#64748B"], "fonts": ["Inter", "Inter", "Inter Tight", "Inter Tight", "Inter"]},
        {"name": "Graphite and mint", "colors": ["#F7F8F7", "#111827", "#34D399", "#E5E7EB", "#1F2937", "#6B7280"], "fonts": ["DM Sans", "DM Sans", "DM Sans", "DM Sans", "DM Sans"]},
    ],
    "Minimal": [
        {"name": "Paper and ink", "colors": ["#FFFFFF", "#111111", "#111111", "#F5F5F5", "#1A1A1A", "#6B6B6B"], "fonts": ["Work Sans", "Work Sans", "Work Sans", "Work Sans", "Work Sans"]},
        {"name": "Stone", "colors": ["#F2F0EC", "#1C1B19", "#8A7F72", "#E7E3DC", "#2A2825", "#7A746B"], "fonts": ["Karla", "Karla", "Karla", "Karla", "Karla"]},
    ],
    "Bold": [
        {"name": "Signal red", "colors": ["#FFF7ED", "#111111", "#EF4444", "#FFE4D6", "#1F1F1F", "#5C5C5C"], "fonts": ["Archivo", "Archivo", "Archivo Black", "Archivo Black", "Archivo"]},
        {"name": "Electric blue", "colors": ["#0B1020", "#FFFFFF", "#3B82F6", "#141B34", "#05070F", "#9CA3AF"], "fonts": ["Space Grotesk", "Space Grotesk", "Space Grotesk", "Space Grotesk", "Space Grotesk"]},
    ],
    "Elegant": [
        {"name": "Ivory and gold", "colors": ["#FBF8F1", "#2B2118", "#B8893B", "#F1EADB", "#3A2E22", "#7B6C5A"], "fonts": ["Lora", "Lora", "Playfair Display", "Playfair Display", "Lora"]},
        {"name": "Midnight and rose", "colors": ["#14111A", "#F5EFF2", "#D98BA3", "#1E1A26", "#0B090F", "#A89BA8"], "fonts": ["Cormorant Garamond", "Cormorant Garamond", "Cormorant Garamond", "Cormorant Garamond", "Cormorant Garamond"]},
    ],
    "Playful": [
        {"name": "Candy", "colors": ["#FFF5FB", "#2D1B4E", "#FF5CA8", "#FFE0F0", "#3B2566", "#7C6A99"], "fonts": ["Nunito", "Nunito", "Baloo 2", "Baloo 2", "Nunito"]},
        {"name": "Sunny", "colors": ["#FFFBEB", "#1F2937", "#F59E0B", "#FEF3C7", "#374151", "#6B7280"], "fonts": ["Fredoka", "Fredoka", "Fredoka", "Fredoka", "Fredoka"]},
    ],
    "Retro": [
        {"name": "Diner", "colors": ["#FDF1DC", "#2E1F14", "#D94F30", "#F6DDB5", "#3F2B1D", "#8A6B4F"], "fonts": ["DM Serif Display", "DM Sans", "DM Serif Display", "DM Serif Display", "DM Sans"]},
        {"name": "Arcade", "colors": ["#12082B", "#F8F4FF", "#22D3EE", "#1E1043", "#0A0418", "#A99CD0"], "fonts": ["Press Start 2P", "Space Mono", "Press Start 2P", "Press Start 2P", "Space Mono"]},
    ],
    "Professional": [
        {"name": "Navy and teal", "colors": ["#F5F7FA", "#102A43", "#0EA5A4", "#E4E9F0", "#183B5C", "#627D98"], "fonts": ["Source Sans 3", "Source Sans 3", "Source Sans 3", "Source Sans 3", "Source Sans 3"]},
        {"name": "Charcoal and green", "colors": ["#F6F7F6", "#1C2321", "#2F855A", "#E6EAE7", "#26302D", "#66736E"], "fonts": ["IBM Plex Sans", "IBM Plex Sans", "IBM Plex Sans", "IBM Plex Sans", "IBM Plex Sans"]},
    ],
}


def normalize_hex(value: str) -> str | None:
    match = _HEX.match((value or "").strip())
    if not match:
        return None
    digits = match.group(1).upper()
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return f"#{digits}"


def _clean_files(items, limit: int = MAX_FILES) -> list[dict]:
    out = []
    for item in items or []:
        url = str((item or {}).get("url") or "")
        if (url.startswith(FILE_URL_PREFIX) or re.fullmatch(r"/api/projects/[A-Za-z0-9_-]+/brand-assets/[a-f0-9]{32}\.png", url)) and ".." not in url:
            out.append({"name": str(item.get("name") or url.rsplit("/", 1)[-1])[:80], "url": url})
    return out[:limit]


def clean_spec(raw: dict | None) -> dict:
    """Validate and normalise a spec. Invalid colors are dropped; unknown keys are ignored."""
    raw = raw or {}
    colors = []
    for item in raw.get("colors") or []:
        hex_value = normalize_hex(str((item or {}).get("hex") or ""))
        name = " ".join(str((item or {}).get("name") or "").split())[:40]
        if hex_value and name:
            colors.append({"name": name, "hex": hex_value})
    fonts = []
    for item in raw.get("fonts") or []:
        family = " ".join(_FONT.sub("", str((item or {}).get("family") or "")).split())[:60]
        role = " ".join(str((item or {}).get("role") or "").split())[:40]
        if family and role:
            fonts.append({"role": role, "family": family})
    return {"colors": colors[:MAX_COLORS], "fonts": fonts[:MAX_FONTS], "logos": _clean_files(raw.get("logos")), "assets": _clean_files(raw.get("assets"))}


def load_spec(raw: str | None) -> dict:
    try:
        return clean_spec(json.loads(raw)) if raw else clean_spec({})
    except json.JSONDecodeError:
        return clean_spec({})


def spec_from_preset(style: str, index: int) -> dict:
    presets = STYLE_PRESETS.get(style) or []
    if not presets:
        raise ValueError("Unknown style.")
    preset = presets[index % len(presets)]
    return clean_spec({
        "colors": [{"name": n, "hex": h} for n, h in zip(COLOR_ROLES, preset["colors"])],
        "fonts": [{"role": r, "family": f} for r, f in zip(FONT_ROLES, preset["fonts"])],
    })


# --- website import ---------------------------------------------------------------------------
def assert_public_url(url: str) -> str:
    """Only http(s) pages on the public internet: no localhost, private ranges or odd ports of this PC."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a web address like example.com.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("That web address could not be found.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("Only public websites can be imported.")
    return parsed.geturl()


def _fetch(url: str, limit: int) -> httpx.Response:
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=False, headers={"User-Agent": "SovereignBrandImport/1.0"}) as client:
        for hop in range(6):
            url = assert_public_url(url)
            with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location or hop == 5:
                        raise ValueError("That website has too many redirects or an invalid redirect.")
                    url = urljoin(str(resp.url), location)
                    continue
                resp.raise_for_status()
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        raise ValueError("That file is too large to import.")
                return httpx.Response(200, content=bytes(body), headers=resp.headers,
                                      request=httpx.Request("GET", str(resp.url)))


_COLOR = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META = re.compile(r"<meta[^>]+>", re.I)
_LINK = re.compile(r"<link[^>]+>", re.I)
_IMG = re.compile(r"<img[^>]+>", re.I)
_ATTR = re.compile(r'([a-zA-Z\-:]+)\s*=\s*["\']([^"\']*)["\']')


def _attrs(tag: str) -> dict:
    return {k.lower(): v for k, v in _ATTR.findall(tag)}


def parse_site(html: str, base_url: str) -> dict:
    """Pull a brand name, the most used colors, font families and logo candidates out of a page."""
    title = _TITLE.search(html)
    metas = [_attrs(m) for m in _META.findall(html)]
    name = next((m.get("content") for m in metas if m.get("property") == "og:site_name" and m.get("content")), None)
    name = (name or (" ".join(title.group(1).split()).split("|")[0].split(" - ")[0] if title else "") or urlparse(base_url).hostname or "").strip()[:80]
    counts: Counter[str] = Counter()
    theme = next((normalize_hex(m.get("content", "")) for m in metas if m.get("name") == "theme-color"), None)
    if theme:
        counts[theme] += 50
    for found in _COLOR.findall(html):
        hex_value = normalize_hex(found)
        if hex_value and hex_value not in {"#FFFFFF", "#000000"}:
            counts[hex_value] += 1
    colors = [c for c, _ in counts.most_common(6)]
    families: Counter[str] = Counter()
    for decl in _FONT_FAMILY.findall(html):
        for family in decl.split(","):
            family = family.strip().strip("'\"")
            if family and family.lower() not in _GENERIC_FONTS and not family.startswith("var("):
                families[_FONT.sub("", family).strip()] += 1
    logos: list[str] = []
    for m in metas:
        if m.get("property") == "og:image" and m.get("content"):
            logos.append(urljoin(base_url, m["content"]))
    for tag in _LINK.findall(html):
        a = _attrs(tag)
        if "icon" in a.get("rel", "").lower() and a.get("href"):
            logos.append(urljoin(base_url, a["href"]))
    for tag in _IMG.findall(html):
        a = _attrs(tag)
        if "logo" in (a.get("src", "") + a.get("alt", "") + a.get("class", "")).lower() and a.get("src"):
            logos.append(urljoin(base_url, a["src"]))
    seen, unique = set(), []
    for item in logos:
        if item not in seen and urlparse(item).scheme in {"http", "https"} and not item.lower().split("?")[0].endswith((".svg", ".ico")):
            seen.add(item)
            unique.append(item)
    return {"name": name, "colors": colors, "fonts": [f for f, _ in families.most_common(3) if f], "logo_candidates": unique[:5]}


def import_site(url: str) -> dict:
    safe = assert_public_url(url)
    try:
        page = _fetch(safe, _PAGE_LIMIT)
    except httpx.HTTPError as exc:
        raise ValueError("That website could not be opened.") from exc
    return {**parse_site(page.text, str(page.request.url)), "url": str(page.request.url)}


def fetch_image(url: str) -> tuple[bytes, str]:
    """Download a public image (png, jpeg or webp, up to 2 MB). Returns (bytes, extension)."""
    safe = assert_public_url(url)
    try:
        resp = _fetch(safe, _IMAGE_LIMIT)
    except httpx.HTTPError as exc:
        raise ValueError("That image could not be downloaded.") from exc
    kind = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(kind)
    if not ext:
        raise ValueError("Only PNG, JPEG or WEBP images can be imported.")
    return resp.content, ext
