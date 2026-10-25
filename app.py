"""
Anghell Convert
Convertidor de YouTube / Shorts a MP3, WAV o MP4 (4K, 1080p, 720p, 480p)
y descargador de sonidos de MyInstants en MP3 o WAV.

Efectos:
- Fondo de piedra estático y lava estilo cartoon animada solo con CSS (muy liviana).
- Lava que sube muy despacio durante 1 minuto hasta la mitad de la pantalla,
  se queda arriba, se vacía y vuelve a empezar (loop).
- Cambio de tema: la lava inunda la pantalla, cambia el tema y la página
  entra girando como una hoja mientras la lava baja.
"""

import hashlib
import html
import inspect
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote

import numpy as np
import requests
import streamlit as st
import streamlit.components.v1 as components
import yt_dlp
from PIL import Image, ImageDraw


# ════════════════════════════ Configuración ════════════════════════════
def make_page_icon() -> Image.Image:
    """Ícono de pestaña dibujado (gota de lava), sin emojis."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for r, c in [(30, (60, 4, 0, 255)), (25, (190, 30, 0, 255)),
                 (18, (255, 95, 0, 255)), (9, (255, 215, 110, 255))]:
        d.ellipse((32 - r, 32 - r, 32 + r, 32 + r), fill=c)
    return img


st.set_page_config(page_title="Anghell Convert", page_icon=make_page_icon(), layout="centered")

for k, v in {"result": None, "sounds": {}, "trimmed": None}.items():
    if k not in st.session_state:
        st.session_state[k] = v


def find_ffmpeg():
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def find_js_runtime():
    """YouTube exige un motor de JavaScript (Deno) para descargar con yt-dlp."""
    path = shutil.which("deno")
    if not path:
        try:
            import deno
            path = deno.find_deno_bin()
        except Exception:
            path = None
    if path:
        return {"deno": {"path": path}}
    node = shutil.which("node")
    if node:
        return {"node": {"path": node}}
    return None


FFMPEG = find_ffmpeg()
JS_RUNTIME = find_js_runtime()

FORMATS = {
    "MP3": {"kind": "audio", "ext": "mp3", "mime": "audio/mpeg"},
    "WAV": {"kind": "audio", "ext": "wav", "mime": "audio/wav"},
    "MP4 4K": {"kind": "video", "ext": "mp4", "mime": "video/mp4", "height": 2160},
    "MP4 1080p": {"kind": "video", "ext": "mp4", "mime": "video/mp4", "height": 1080},
    "MP4 720p": {"kind": "video", "ext": "mp4", "mime": "video/mp4", "height": 720},
    "MP4 480p": {"kind": "video", "ext": "mp4", "mime": "video/mp4", "height": 480},
}

YT_REGEX = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com/(watch\?v=|shorts/|live/|embed/)|youtu\.be/)[\w\-]{6,}",
    re.IGNORECASE,
)

MI_BASE = "https://www.myinstants.com"
MI_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}
MI_MAX_RESULTS = 12


# ════════════════════════════ Íconos dibujados (SVG) ════════════════════════════
def icon_uri(inner: str) -> str:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
        "stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
        + inner + "</svg>"
    )
    return "url(\"data:image/svg+xml;utf8," + quote(svg) + "\")"


ICONS = {
    "__I_NOTE__": icon_uri("<path d='M9 18V5l11-2v13'/><circle cx='6.5' cy='18' r='2.5'/>"
                           "<circle cx='17.5' cy='16' r='2.5'/>"),
    "__I_WAVE__": icon_uri("<path d='M3 12h1.5M7 8.5v7M11 4v16M15 7v10M19 9.5v5M21.5 12h-.5'/>"),
    "__I_FILM__": icon_uri("<rect x='3' y='5' width='18' height='14' rx='3'/>"
                           "<path d='M10 9.5v5l4.3-2.5z'/>"),
    "__I_SPEAKER__": icon_uri("<path d='M4 9.5h3.5L12 5.5v13l-4.5-4H4z'/>"
                              "<path d='M15.5 9a4 4 0 0 1 0 6'/><path d='M18.5 6.5a7.5 7.5 0 0 1 0 11'/>"),
    "__I_CONVERT__": icon_uri("<path d='M4 12a8 8 0 0 1 13.7-5.6L20 8.5'/><path d='M20 4v4.5h-4.5'/>"
                              "<path d='M20 12a8 8 0 0 1-13.7 5.6L4 15.5'/><path d='M4 20v-4.5h4.5'/>"),
    "__I_DOWNLOAD__": icon_uri("<path d='M12 4v11'/><path d='M7 10.5l5 5 5-5'/><path d='M5 20h14'/>"),
}

CRUST = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='320'>"
    "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.024' numOctaves='3' seed='11'/>"
    "<feColorMatrix values='0 0 0 0 0.13  0 0 0 0 0.015  0 0 0 0 0  3.2 0 0 0 -1.55'/></filter>"
    "<rect width='100%' height='100%' filter='url(#n)'/></svg>"
)
ICONS["__TILE_DARK__"] = "url(\"data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%27http%3A//www.w3.org/2000/svg%27%20width%3D%27132%27%20height%3D%2788%27%3E%3Cg%20fill%3D%27%231c0c0a%27%20stroke%3D%27%230d0504%27%20stroke-width%3D%273%27%3E%3Crect%20x%3D%272%27%20y%3D%272%27%20width%3D%2760%27%20height%3D%2740%27%20rx%3D%279%27/%3E%3Crect%20x%3D%2768%27%20y%3D%272%27%20width%3D%2762%27%20height%3D%2740%27%20rx%3D%279%27/%3E%3Crect%20x%3D%27-31%27%20y%3D%2746%27%20width%3D%2760%27%20height%3D%2740%27%20rx%3D%279%27/%3E%3Crect%20x%3D%2735%27%20y%3D%2746%27%20width%3D%2762%27%20height%3D%2740%27%20rx%3D%279%27/%3E%3Crect%20x%3D%27103%27%20y%3D%2746%27%20width%3D%2760%27%20height%3D%2740%27%20rx%3D%279%27/%3E%3C/g%3E%3C/svg%3E\")"
ICONS["__TILE_LIGHT__"] = "url(\"data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%27http%3A//www.w3.org/2000/svg%27%20width%3D%27132%27%20height%3D%2788%27%3E%3Cg%20fill%3D%27%23f1dcc6%27%20stroke%3D%27%23e2c4a6%27%20stroke-width%3D%273%27%3E%3Crect%20x%3D%272%27%20y%3D%272%27%20width%3D%2760%27%20height%3D%2740%27%20rx%3D%279%27/%3E%3Crect%20x%3D%2768%27%20y%3D%272%27%20width%3D%2762%27%20height%3D%2740%27%20rx%3D%279%27/%3E%3Crect%20x%3D%27-31%27%20y%3D%2746%27%20width%3D%2760%27%20height%3D%2740%27%20rx%3D%279%27/%3E%3Crect%20x%3D%2735%27%20y%3D%2746%27%20width%3D%2762%27%20height%3D%2740%27%20rx%3D%279%27/%3E%3Crect%20x%3D%27103%27%20y%3D%2746%27%20width%3D%2760%27%20height%3D%2740%27%20rx%3D%279%27/%3E%3C/g%3E%3C/svg%3E\")"
ICONS["__CRUST__"] = "url(\"data:image/svg+xml;utf8," + quote(CRUST) + "\")"


# ════════════════════════════ Estilos ════════════════════════════
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Unbounded:wght@500;700;900&family=Manrope:wght@400;500;600;700&display=swap');

:root {
  --bg: #060303;
  --panel: rgba(12, 6, 5, 0.80);
  --pill: rgba(22, 10, 8, 0.72);
  --text: #fbefe6;
  --muted: #b39d92;
  --border: rgba(255, 90, 30, 0.30);
  --input: rgba(8, 4, 3, 0.86);
  --glow: rgba(255, 60, 0, 0.38);
  --lava: linear-gradient(100deg, #6e0800, #ff2a00 18%, #ffb000 32%, #ff4a00 48%,
                          #9a0e00 62%, #ff6a00 78%, #ffd36a 88%, #b81400);
  color-scheme: dark;
  --vignette: rgba(0, 0, 0, .65);
  --tile: __TILE_DARK__;
}
:root[data-ac-theme="light"] {
  --bg: #f3e7dc;
  --panel: rgba(255, 249, 243, 0.86);
  --pill: rgba(255, 255, 255, 0.80);
  --text: #1c0a04;
  --muted: #6e4f40;
  --border: rgba(200, 60, 10, 0.32);
  --input: rgba(255, 255, 255, 0.94);
  --glow: rgba(255, 90, 20, 0.25);
  color-scheme: light;
  --vignette: rgba(120, 60, 20, .18);
  --tile: __TILE_LIGHT__;
}

/* El fondo pintado va en <html>; todo lo demás transparente para que la lava
   (z-index -1) quede DETRÁS del convertidor y el convertidor siempre visible. */
body, #root, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"],
[data-testid="stBottom"], [data-testid="stBottomBlockContainer"] { background: transparent !important; }
.stApp, .stApp p, .stApp label, .stApp input, .stApp button, .stApp textarea {
  font-family: 'Manrope', system-ui, sans-serif;
}
[data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }
.stApp { color: var(--text); }
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }

/* ─────────────── Lava cartoon (solo transform/opacity: muy liviana) ─────────────── */
html { background-color: var(--bg) !important;
  background-image: radial-gradient(ellipse at 50% 30%, transparent 40%, var(--vignette) 100%), var(--tile) !important;
  background-size: 100% 100%, 132px 88px !important; background-attachment: fixed !important; }
#ac-lava { position: fixed; inset: 0; z-index: -1; pointer-events: none; overflow: hidden; contain: strict; }
#ac-lava.ac-flood { z-index: 999990; }
.ac-surge { position: absolute; inset: 0; transform: translateY(0);
  transition: transform 1.1s cubic-bezier(.3, .7, .3, 1); will-change: transform; }
.ac-surge.ac-up { transform: translateY(-112vh); transition: transform .75s cubic-bezier(.6, 0, .9, .6); }
.ac-level { position: absolute; left: 0; right: 0; top: 100%; height: 230vh;
  animation: ac-level 100s infinite; will-change: transform; }
@keyframes ac-level {
  0%   { transform: translateY(-3vh);  animation-timing-function: cubic-bezier(.45, 0, .55, 1); }
  60%  { transform: translateY(-50vh); animation-timing-function: linear; }
  72%  { transform: translateY(-50vh); animation-timing-function: cubic-bezier(.45, 0, .55, 1); }
  96%  { transform: translateY(-3vh); }
  100% { transform: translateY(-3vh); }
}
.ac-heat { position: absolute; left: 0; right: 0; top: -150px; height: 150px;
  background: linear-gradient(to top, rgba(255, 110, 20, .28), transparent); }
.ac-body { position: absolute; inset: 0;
  background: linear-gradient(to bottom, #ffa526 0, #ff7a1a 70px, #f2501a 32vh, #c8300f 70vh, #8f1f0b 100%); }
.ac-body::before { content: ""; position: absolute; left: 0; right: 0; top: 10px; height: 26px;
  background: linear-gradient(to bottom, rgba(255, 236, 160, .35), transparent); }
.ac-lwave { position: absolute; left: 0; top: -38px; width: 200%; height: 40px;
  animation: ac-wave 7s linear infinite; will-change: transform; }
.ac-lwave.back { top: -50px; animation-duration: 11s; animation-direction: reverse; opacity: .75; }
.ac-lwave svg { width: 100%; height: 100%; display: block; }
@keyframes ac-wave { from { transform: translateX(0); } to { transform: translateX(-50%); } }
.ac-bubble { position: absolute; top: 0; border-radius: 50%;
  background: rgba(255, 214, 120, .55); box-shadow: inset -2px -2px 0 rgba(255, 255, 255, .35);
  animation: ac-bubble linear infinite; will-change: transform, opacity; opacity: 0; }
@keyframes ac-bubble {
  0%   { transform: translateY(42vh) scale(.6); opacity: 0; }
  15%  { opacity: 1; }
  88%  { transform: translateY(14px) scale(1); opacity: 1; }
  100% { transform: translateY(0) scale(1.5); opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .ac-level { animation: none; transform: translateY(-18vh); }
  .ac-lwave, .ac-bubble { animation: none; }
}

div[data-testid="stElementContainer"]:has(iframe),
div[data-testid="stElementContainer"]:has(.ac-engine-host),
.element-container:has(iframe) { display: none !important; }

/* Panel de vidrio que gira como una página */
[data-testid="stMain"], section.main { perspective: 1800px; }
.block-container, [data-testid="stMainBlockContainer"] {
  max-width: 780px;
  margin-top: 1.6rem; margin-bottom: 4rem;
  padding: 1.2rem 2.2rem 1.6rem !important;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 26px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, .35);
}
.ac-flip { animation: ac-pageflip 1.35s cubic-bezier(.16, .84, .24, 1) both;
           transform-origin: left center; }
@keyframes ac-pageflip {
  0%   { transform: rotateY(-105deg) translateZ(40px); opacity: 0; filter: brightness(1.8) sepia(.6); }
  25%  { opacity: 1; }
  70%  { transform: rotateY(6deg); filter: none; }
  100% { transform: rotateY(0); }
}

/* Botón de tema (lo crea el motor JS) */
#ac-theme-toggle {
  position: fixed; top: calc(16px + env(safe-area-inset-top, 0px)); right: 18px; z-index: 1000;
  display: inline-flex; align-items: center; gap: .5rem;
  padding: .55rem 1rem; border-radius: 999px;
  border: 1px solid var(--border); background: var(--panel); color: var(--text);
  font: 600 .86rem 'Manrope', system-ui, sans-serif; cursor: pointer;
  box-shadow: 0 4px 20px var(--glow); transition: transform .2s, box-shadow .2s;
}
#ac-theme-toggle:hover { transform: translateY(-1px); box-shadow: 0 6px 28px var(--glow); }
#ac-theme-toggle:focus-visible { outline: 2px solid #ff9a00; outline-offset: 3px; }
#ac-theme-toggle svg { width: 18px; height: 18px; fill: none; stroke: currentColor;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
#ac-theme-toggle .ac-ico-sun { color: #ffae1f; }
#ac-theme-toggle .ac-ico-moon { display: none; color: #b8320a; }
:root[data-ac-theme="light"] #ac-theme-toggle .ac-ico-moon { display: block; }
:root[data-ac-theme="light"] #ac-theme-toggle .ac-ico-sun { display: none; }
#ac-theme-toggle.ac-busy { pointer-events: none; }

/* ─────────────── Logo de lava ─────────────── */
.ac-hero { text-align: center; margin: 0 auto 1.2rem; display: flex; flex-direction: column; align-items: center; }
.ac-emblem { display: inline-block; position: relative; }
.ac-emblem svg { width: 74px; height: 74px; display: block; position: relative; }
.ac-emblem::before { content: ""; position: absolute; inset: -14px; border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 110, 0, .55), transparent 65%);
  animation: ac-pulse 3.2s ease-in-out infinite; }
@keyframes ac-pulse { 0%, 100% { opacity: .45; transform: scale(.92); } 50% { opacity: 1; transform: scale(1.05); } }
.ac-ring { transform-box: fill-box; transform-origin: center; animation: ac-spin 22s linear infinite; }
@keyframes ac-spin { to { transform: rotate(360deg); } }
.ac-s1 { stop-color: #fff2b8; animation: ac-s1 2.6s ease-in-out infinite alternate; }
.ac-s2 { stop-color: #ff6a00; animation: ac-s2 3.4s ease-in-out infinite alternate; }
.ac-s3 { stop-color: #7a0900; animation: ac-s3 4.2s ease-in-out infinite alternate; }
@keyframes ac-s1 { to { stop-color: #ffbe3c; } }
@keyframes ac-s2 { to { stop-color: #ff2c00; } }
@keyframes ac-s3 { to { stop-color: #3c0200; } }

.ac-wordwrap { position: relative; display: inline-block; margin-top: .35rem; }
.ac-word {
  font-family: 'Unbounded', sans-serif; font-weight: 900;
  font-size: clamp(2.2rem, 7.6vw, 4.1rem); line-height: 1.04; letter-spacing: -.025em;
  background-image: __CRUST__, var(--lava);
  background-size: 320px 320px, 320% 100%;
  -webkit-background-clip: text; background-clip: text; color: transparent;
  background-position: 0 0, 30% 50%;
  text-shadow: none;
  filter: drop-shadow(0 0 12px rgba(255, 70, 0, .5));
  padding: 0 .08em;
}
@keyframes ac-molten {
  0%   { background-position: 0 0, 0% 50%; }
  100% { background-position: 320px -160px, 320% 50%; }
}
.ac-drips { position: absolute; left: 0; right: 0; bottom: .16em; height: 0; }
.ac-drips i {
  position: absolute; top: 0; width: 7px; height: 0; border-radius: 0 0 8px 8px;
  background: linear-gradient(#ff4a00, #ffae2e);
  box-shadow: 0 0 10px rgba(255, 110, 0, .7);
  animation: ac-drip 6s ease-in infinite; animation-delay: var(--d);
}
.ac-drips i::after {
  content: ""; position: absolute; left: 50%; bottom: -7px; width: 9px; height: 11px;
  margin-left: -4.5px; border-radius: 50% 50% 50% 50% / 60% 60% 40% 40%;
  background: #ffb43a; box-shadow: 0 0 12px rgba(255, 140, 0, .9);
  opacity: 0; animation: ac-fall 6s ease-in infinite; animation-delay: var(--d);
}
@keyframes ac-drip { 0% { height: 0 } 55% { height: 16px } 66% { height: 20px }
                     80% { height: 6px } 100% { height: 0 } }
@keyframes ac-fall { 0%, 62% { opacity: 0; transform: translateY(0) }
                     64% { opacity: 1 } 100% { opacity: 0; transform: translateY(34px) scale(.6) } }
.ac-hero .ac-sub { color: var(--muted) !important; font-size: 1.02rem; text-align: center !important;
  margin: 1.5rem auto 0 !important; max-width: 46ch; width: 100%; padding: 0 !important; }

/* ─────────────── Pestañas ─────────────── */
.stTabs [data-baseweb="tab-list"] { gap: .35rem; border-bottom: 1px solid var(--border); }
.stTabs [data-baseweb="tab-border"] { display: none; }
.stTabs [data-baseweb="tab"] {
  background: transparent; color: var(--muted); padding: .65rem 1rem; border-radius: 12px 12px 0 0;
  display: inline-flex; align-items: center; transition: color .2s, background .2s; }
.stTabs [data-baseweb="tab"] p { color: inherit !important; font-weight: 700; font-size: .98rem; }
.stTabs [data-baseweb="tab"]:hover { color: var(--text); background: var(--pill); }
.stTabs [data-baseweb="tab"][aria-selected="true"] { color: var(--text); }
.stTabs [data-baseweb="tab-highlight"] { background: linear-gradient(90deg, #ff2a00, #ffb000) !important;
  height: 3px; border-radius: 3px; }
.stTabs [data-baseweb="tab"]::before {
  content: ""; width: 17px; height: 17px; margin-right: .5rem; background: currentColor;
  -webkit-mask: __I_FILM__ center / contain no-repeat; mask: __I_FILM__ center / contain no-repeat; }
.stTabs [data-baseweb="tab"]:nth-child(2)::before {
  -webkit-mask-image: __I_SPEAKER__; mask-image: __I_SPEAKER__; }
.stTabs [data-baseweb="tab"][aria-selected="true"]::before { background: #ff5a00; }

/* ─────────────── Controles ─────────────── */
.stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp label { color: var(--text); }
[data-testid="stWidgetLabel"] p { color: var(--muted) !important; font-weight: 600; }

.stTextInput input {
  background: var(--input) !important; color: var(--text) !important;
  border: 1px solid var(--border) !important; border-radius: 14px !important;
  padding: .9rem 1.05rem !important; font-size: 1rem !important;
  transition: border-color .2s, box-shadow .2s;
}
.stTextInput input::placeholder { color: var(--muted) !important; opacity: .7; }
.stTextInput input:focus { border-color: #ff5a1f !important; box-shadow: 0 0 0 3px var(--glow) !important; }
.stTextInput [data-baseweb="input"], .stTextInput [data-baseweb="base-input"] {
  background: transparent !important; border: none !important; }

div[role="radiogroup"] { gap: .55rem !important; flex-wrap: wrap; }
[data-testid="stRadioOption"] {
  display: inline-flex !important; align-items: center;
  background: var(--pill); border: 1px solid var(--border); border-radius: 999px;
  padding: .5rem 1rem !important; margin: 0 !important; cursor: pointer;
  transition: border-color .2s, box-shadow .2s, transform .2s;
}
[data-testid="stRadioOption"]:hover { transform: translateY(-1px); border-color: rgba(255, 90, 30, .6); }
[data-testid="stRadioOption"] > div > div:first-child:not([data-testid]) { display: none !important; }
[data-testid="stRadioOption"] p { color: var(--text) !important; font-weight: 600; margin: 0 !important; }
[data-testid="stRadioOption"]::before {
  content: ""; width: 17px; height: 17px; margin-right: .5rem; flex-shrink: 0; background: var(--muted);
  -webkit-mask: __I_FILM__ center / contain no-repeat; mask: __I_FILM__ center / contain no-repeat; }
div[role="radiogroup"] > div:nth-child(1) [data-testid="stRadioOption"]::before {
  -webkit-mask-image: __I_NOTE__; mask-image: __I_NOTE__; }
div[role="radiogroup"] > div:nth-child(2) [data-testid="stRadioOption"]::before {
  -webkit-mask-image: __I_WAVE__; mask-image: __I_WAVE__; }
[data-testid="stRadioOption"][data-selected="true"] {
  border-color: #ff4d00; background: linear-gradient(180deg, rgba(255, 80, 0, .16), rgba(255, 80, 0, .05)), var(--pill);
  box-shadow: 0 0 16px var(--glow); }
[data-testid="stRadioOption"][data-selected="true"]::before { background: #ff5a00; }
[data-testid="stRadioOption"]:has(input:focus-visible) { outline: 2px solid #ff9a00; outline-offset: 2px; }

.stButton > button, .stDownloadButton > button {
  width: 100%; border: none !important; border-radius: 14px !important;
  padding: .85rem 1rem !important; color: #fff !important;
  background: var(--lava) !important; background-size: 320% 100% !important;
  background-position: 20% 50% !important;
  box-shadow: 0 8px 28px var(--glow); transition: transform .15s, box-shadow .2s, background-position .8s ease;
}
.stButton > button p, .stDownloadButton > button p {
  font-family: 'Unbounded', sans-serif !important; font-weight: 700; color: #fff !important;
  text-shadow: 0 1px 2px rgba(60, 4, 0, .6); }
.stButton > button::before, .stDownloadButton > button::before {
  content: ""; width: 18px; height: 18px; margin-right: .55rem; flex-shrink: 0; background: #fff;
  -webkit-mask: __I_CONVERT__ center / contain no-repeat; mask: __I_CONVERT__ center / contain no-repeat; }
.stDownloadButton > button::before, [class*="st-key-mi_prep_"] button::before {
  -webkit-mask-image: __I_DOWNLOAD__; mask-image: __I_DOWNLOAD__; }
.stButton > button:hover, .stDownloadButton > button:hover {
  transform: translateY(-2px); box-shadow: 0 12px 36px var(--glow); background-position: 80% 50% !important; }
.stButton > button:disabled { filter: grayscale(.7) brightness(.8); opacity: .6; }
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible {
  outline: 2px solid #ff9a00 !important; outline-offset: 3px; }
@keyframes ac-btnflow { to { background-position: 320% 50%; } }

/* Botones secundarios en la lista de sonidos */
[class*="st-key-mi_prep_"] button {
  background: var(--pill) !important; border: 1px solid var(--border) !important;
  animation: none !important; box-shadow: none !important; padding: .6rem .8rem !important; }
[class*="st-key-mi_prep_"] button p { color: var(--text) !important; text-shadow: none;
  font-family: 'Manrope', sans-serif !important; font-size: .9rem; }
[class*="st-key-mi_prep_"] button::before { background: var(--text); }
[class*="st-key-mi_prep_"] button:hover { border-color: #ff4d00 !important; }
[class*="st-key-mi_dl_"] button { padding: .6rem .8rem !important; }
[class*="st-key-mi_dl_"] button p { font-family: 'Manrope', sans-serif !important; font-size: .9rem; }

/* Tarjetas */
[data-testid="stVerticalBlockBorderWrapper"]:has(.ac-sound) {
  background: var(--pill); border: 1px solid var(--border) !important; border-radius: 16px;
  animation: ac-in .4s ease-out both; }
.ac-sound { font-weight: 700; color: var(--text); line-height: 1.3; padding-top: .35rem; word-break: break-word; }
[data-testid="stAudio"] audio, audio { width: 100%; height: 40px; }

.ac-card {
  display: flex; gap: 1rem; align-items: center;
  background: var(--pill); border: 1px solid var(--border); border-radius: 18px;
  padding: .9rem; margin: .9rem 0 1.2rem; animation: ac-in .5s ease-out both;
}
@keyframes ac-in { from { opacity: 0; transform: translateY(6px); } }
.ac-card img { width: 168px; border-radius: 12px; flex-shrink: 0; }
.ac-card .t { font-weight: 700; color: var(--text); line-height: 1.3; }
.ac-card .m { color: var(--muted); font-size: .9rem; margin-top: .35rem; }

[data-testid="stExpander"] details { background: var(--pill); border: 1px solid var(--border) !important;
  border-radius: 14px; }
[data-testid="stExpander"] summary p { color: var(--muted) !important; font-weight: 600; }
[data-testid="stFileUploaderDropzone"] { background: var(--input) !important; border: 1px dashed var(--border) !important; }

.stProgress > div > div > div > div,
[data-testid="stProgress"] [role="progressbar"] > div > div {
  background: var(--lava) !important; background-size: 320% 100% !important;
  animation: ac-btnflow 3s linear infinite; }

/* Editor de recorte */
.ac-trim-title { font-family: 'Unbounded', sans-serif; font-weight: 700; font-size: 1.05rem;
  color: var(--text); margin: 1.4rem 0 .2rem; }
.ac-wave { background: var(--input); border: 1px solid var(--border); border-radius: 16px;
  padding: 10px 14px; margin-bottom: -.4rem; }
.ac-wave svg { width: 100%; height: 120px; display: block; }
.ac-wave .wf-off { fill: var(--muted); opacity: .28; }
.ac-wave .wf-on { fill: url(#wfLava); }
.ac-wave .wf-region { fill: rgba(255, 90, 0, .10); stroke: #ff5a00; stroke-width: 2; }
.ac-wave .wf-handle { fill: #ff5a00; }
.ac-wave .wf-grip { fill: #fff3d6; }
[data-testid="stSlider"] { padding: 0 14px; }
[data-testid="stSlider"] [role="slider"] { background: #ff5a00 !important; border: 3px solid #ffd36a !important;
  box-shadow: 0 0 12px var(--glow) !important; width: 18px !important; height: 18px !important; }
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {
  color: var(--muted) !important; font-family: 'Manrope', sans-serif !important; }
.ac-trim-times { display: flex; justify-content: space-between; gap: 1rem; color: var(--muted);
  font-size: .9rem; margin: -.3rem 14px .8rem; }
.ac-trim-times b { color: var(--text); font-variant-numeric: tabular-nums; }
[data-testid="stToggle"] p { color: var(--text) !important; }

.ac-foot { color: var(--muted) !important; font-size: .8rem; text-align: center; margin-top: 2.2rem; }

@media (max-width: 640px) {
  .block-container, [data-testid="stMainBlockContainer"] {
    margin: 4.2rem .6rem 2rem; padding: 1.5rem 1.1rem 1.2rem !important; border-radius: 20px; }
  .ac-card { flex-direction: column; align-items: flex-start; }
  .ac-card img { width: 100%; }
  #ac-theme-toggle .ac-tlabel { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .ac-word, .ac-emblem, .ac-ring, .ac-drips i, .ac-drips i::after,
  .stButton > button, .stDownloadButton > button { animation: none !important; }
}
</style>
"""
for key, val in ICONS.items():
    CSS = CSS.replace(key, val)

st.markdown(CSS, unsafe_allow_html=True)


# ════════════════════════════ Logo central ════════════════════════════
LOGO = """
<div class="ac-hero">
  <div class="ac-emblem" aria-hidden="true">
    <svg viewBox="0 0 120 120">
      <defs>
        <radialGradient id="acCore" cx="50%" cy="64%" r="62%">
          <stop offset="0%" class="ac-s1"/>
          <stop offset="48%" class="ac-s2"/>
          <stop offset="100%" class="ac-s3"/>
        </radialGradient>
        <linearGradient id="acRing" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#ff1a00"/>
          <stop offset="55%" stop-color="#ff9a00"/>
          <stop offset="100%" stop-color="#3a0400"/>
        </linearGradient>
      </defs>
      <circle class="ac-ring" cx="60" cy="60" r="55" fill="none" stroke="url(#acRing)"
              stroke-width="3" stroke-dasharray="7 11" stroke-linecap="round"/>
      <circle cx="60" cy="60" r="46" fill="none" stroke="url(#acRing)" stroke-width="1.3" opacity=".55"/>
      <path d="M60 17 C60 17 31 52 31 73 a29 29 0 0 0 58 0 C89 52 60 17 60 17 Z" fill="url(#acCore)"/>
      <path d="M47 72 q3 -15 13 -27" stroke="#fff0bf" stroke-width="3.2" fill="none"
            stroke-linecap="round" opacity=".8"/>
      <path d="M41 86 q19 11 38 0" stroke="#3a0400" stroke-width="3" fill="none"
            stroke-linecap="round" opacity=".5"/>
    </svg>
  </div>
  <div></div>
  <div class="ac-wordwrap">
    <div class="ac-word" role="heading" aria-level="1">Anghell Convert</div>
    <div class="ac-drips" aria-hidden="true">
      <i style="left:9%;--d:0s"></i><i style="left:27%;--d:2.3s"></i>
      <i style="left:49%;--d:4.1s"></i><i style="left:68%;--d:1.2s"></i>
      <i style="left:88%;--d:3.2s"></i>
    </div>
  </div>
  <p class="ac-sub">Convierte videos de YouTube y descarga sonidos de MyInstants.</p>
</div>
"""
st.markdown(LOGO, unsafe_allow_html=True)


# ════════════════════════════ Errores legibles ════════════════════════════
def explain_error(err: Exception) -> str:
    low = str(err).lower()
    if isinstance(err, requests.exceptions.RequestException):
        return "No hubo respuesta del sitio. Revisa tu conexión a internet e inténtalo de nuevo."
    if "sign in to confirm" in low or "not a bot" in low:
        return ("YouTube bloqueó la descarga desde este servidor con su verificación anti-bot. "
                "Sube tu archivo de cookies de YouTube en Opciones avanzadas o ejecuta la app en tu computador.")
    if "javascript" in low or "challenge" in low or "js runtime" in low or "ejs" in low:
        return ("Falta el motor de JavaScript que YouTube ahora exige. Reinstala las dependencias con "
                "pip install -r requirements.txt (incluye deno y yt-dlp-ejs).")
    if "ffmpeg" in low or "ffprobe" in low:
        return "FFmpeg no está disponible. Reinstala las dependencias o instala FFmpeg en el sistema."
    if "requested format is not available" in low:
        return "YouTube no entregó ese formato para este video. Prueba con otra calidad."
    if "private video" in low:
        return "El video es privado."
    if "age" in low and ("confirm" in low or "restricted" in low):
        return "El video tiene restricción de edad. Sube tus cookies de YouTube en Opciones avanzadas."
    if "http error 403" in low or "forbidden" in low:
        return "YouTube rechazó la descarga (403). Actualiza yt-dlp con pip install -U \"yt-dlp[default]\"."
    if "unavailable" in low:
        return "El video no está disponible en esta región o fue eliminado."
    return "No se pudo completar la operación."


def show_error(err: Exception, prefix: str = ""):
    st.error((prefix + " " if prefix else "") + explain_error(err))
    with st.expander("Detalle técnico"):
        st.code(str(err)[:3000], language=None)


# ════════════════════════════ YouTube ════════════════════════════
def base_opts(cookiefile=None) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "retries": 3, "fragment_retries": 3, "concurrent_fragment_downloads": 4}
    if FFMPEG:
        opts["ffmpeg_location"] = FFMPEG
    if JS_RUNTIME:
        opts["js_runtimes"] = JS_RUNTIME
    if cookiefile:
        opts["cookiefile"] = cookiefile
    return opts


@st.cache_data(ttl=900, show_spinner=False)
def get_info(url: str, cookiefile=None) -> dict:
    with yt_dlp.YoutubeDL({**base_opts(cookiefile), "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    heights = sorted({f.get("height") for f in info.get("formats") or [] if f.get("height")})
    return {
        "title": info.get("title") or "Sin título",
        "uploader": info.get("uploader") or "",
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("thumbnail"),
        "max_height": heights[-1] if heights else 0,
    }


def fmt_duration(sec) -> str:
    m, s = divmod(int(sec or 0), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_candidates(choice: str):
    cfg = FORMATS[choice]
    if cfg["kind"] == "audio":
        return ["bestaudio/best", "best"]
    h = cfg["height"]
    return [
        f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/bv*[height<={h}]+ba/b[height<={h}]",
        f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b",
        "b",
    ]


def convert(url: str, choice: str, cookiefile=None):
    cfg = FORMATS[choice]
    bar = st.progress(0, text="Preparando")

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            pct = min(done / total, 1.0) if total else 0
            bar.progress(pct, text=f"Descargando {pct * 100:.0f}%")
        elif d["status"] == "finished":
            bar.progress(1.0, text="Convirtiendo con FFmpeg")

    last_err = None
    for fmt in format_candidates(choice):
        outdir = tempfile.mkdtemp(prefix="anghell_")
        try:
            opts = {**base_opts(cookiefile),
                    "outtmpl": os.path.join(outdir, "%(title).90s.%(ext)s"),
                    "progress_hooks": [hook], "format": fmt}
            if cfg["kind"] == "audio":
                pp = {"key": "FFmpegExtractAudio", "preferredcodec": cfg["ext"]}
                if cfg["ext"] == "mp3":
                    pp["preferredquality"] = "320"
                opts["postprocessors"] = [pp]
            else:
                opts["merge_output_format"] = "mp4"
                opts["postprocessors"] = [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}]

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            files = [f for f in os.listdir(outdir) if f.lower().endswith("." + cfg["ext"])]
            if not files:
                raise RuntimeError("FFmpeg no generó el archivo final.")
            path = max((os.path.join(outdir, f) for f in files), key=os.path.getsize)
            with open(path, "rb") as fh:
                data = fh.read()
            bar.progress(1.0, text="Listo")
            return {"name": os.path.basename(path), "data": data, "mime": cfg["mime"]}
        except yt_dlp.utils.DownloadError as e:
            last_err = e
            if "requested format is not available" not in str(e).lower():
                break
        finally:
            shutil.rmtree(outdir, ignore_errors=True)
    bar.empty()
    raise last_err or RuntimeError("Error desconocido.")


# ════════════════════════════ Editor de recorte (estilo Discord) ════════════════════════════
@st.cache_data(show_spinner=False, max_entries=6)
def waveform_peaks(data: bytes, ext: str, bars: int = 160):
    """Decodifica el audio a mono y devuelve picos normalizados + duración en segundos."""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in." + ext)
        with open(src, "wb") as fh:
            fh.write(data)
        proc = subprocess.run([FFMPEG, "-v", "error", "-i", src, "-ac", "1", "-ar", "8000",
                               "-f", "s16le", "pipe:1"], capture_output=True, check=True)
    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    duration = len(samples) / 8000.0
    if len(samples) == 0:
        return [0.0] * bars, 0.0
    chunks = np.array_split(np.abs(samples), bars)
    peaks = np.array([float(np.sqrt(np.mean(c ** 2))) if len(c) else 0.0 for c in chunks])
    peaks = peaks / (peaks.max() or 1.0)
    return [round(float(p), 3) for p in np.clip(peaks ** 0.75, 0.04, 1.0)], duration


def waveform_svg(peaks, start: float, end: float, duration: float) -> str:
    n, W, H = len(peaks), 1000, 120
    bw = W / n
    s_frac, e_frac = (start / duration, end / duration) if duration else (0, 1)
    bars = []
    for i, p in enumerate(peaks):
        h = max(4, p * (H - 24))
        x, y = i * bw + bw * 0.18, (H - h) / 2
        inside = s_frac <= (i + 0.5) / n <= e_frac
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * 0.64:.1f}" height="{h:.1f}" rx="{bw * 0.32:.1f}" '
                    f'class="{"wf-on" if inside else "wf-off"}"/>')
    sx, ex = s_frac * W, e_frac * W
    return f"""
<div class="ac-wave">
  <svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label="Forma de onda del audio">
    <defs><linearGradient id="wfLava" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffd36a"/><stop offset="50%" stop-color="#ff5a00"/>
      <stop offset="100%" stop-color="#c41a00"/></linearGradient></defs>
    <rect x="{sx:.1f}" y="2" width="{max(ex - sx, 0):.1f}" height="{H - 4}" rx="10" class="wf-region"/>
    {''.join(bars)}
    <rect x="{sx - 5:.1f}" y="0" width="10" height="{H}" rx="5" class="wf-handle"/>
    <rect x="{ex - 5:.1f}" y="0" width="10" height="{H}" rx="5" class="wf-handle"/>
    <rect x="{sx - 1.5:.1f}" y="{H / 2 - 14}" width="3" height="28" rx="1.5" class="wf-grip"/>
    <rect x="{ex - 1.5:.1f}" y="{H / 2 - 14}" width="3" height="28" rx="1.5" class="wf-grip"/>
  </svg>
</div>"""


def fmt_time(sec: float) -> str:
    m, s = divmod(max(sec, 0), 60)
    return f"{int(m)}:{s:04.1f}"


def trim_audio(data: bytes, ext: str, start: float, end: float, fade: bool) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in." + ext), os.path.join(d, "out." + ext)
        with open(src, "wb") as fh:
            fh.write(data)
        length = max(end - start, 0.1)
        cmd = [FFMPEG, "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", src]
        if fade:
            f = min(0.4, length / 4)
            cmd += ["-af", f"afade=t=in:st=0:d={f:.2f},afade=t=out:st={length - f:.3f}:d={f:.2f}"]
        cmd += ["-c:a", "libmp3lame", "-b:a", "320k"] if ext == "mp3" else ["-c:a", "pcm_s16le"]
        subprocess.run(cmd + [dst], check=True, capture_output=True)
        with open(dst, "rb") as fh:
            return fh.read()


def audio_trimmer(result: dict):
    ext = result["name"].rsplit(".", 1)[-1].lower()
    try:
        peaks, duration = waveform_peaks(result["data"], ext)
    except Exception as e:
        show_error(e, "No se pudo leer el audio para recortarlo.")
        return
    if duration <= 0.2:
        return
    uid = hashlib.md5(result["name"].encode()).hexdigest()[:8]
    st.markdown('<div class="ac-trim-title">Recortar audio</div>', unsafe_allow_html=True)
    wave_slot = st.empty()
    start, end = st.slider("Selección", 0.0, float(round(duration, 1)), (0.0, float(round(duration, 1))),
                           step=0.1, key=f"trim_{uid}", label_visibility="collapsed", format="%.1f s")
    if end - start < 0.2:
        end = min(duration, start + 0.2)
    wave_slot.markdown(waveform_svg(peaks, start, end, duration), unsafe_allow_html=True)
    st.markdown(
        f'<div class="ac-trim-times"><span>Inicio <b>{fmt_time(start)}</b></span>'
        f'<span>Duración <b>{fmt_time(end - start)}</b></span>'
        f'<span>Fin <b>{fmt_time(end)}</b></span></div>', unsafe_allow_html=True)
    st.audio(result["data"], format=result["mime"], start_time=float(start), end_time=float(end))
    fade = st.toggle("Suavizar inicio y final", value=False, key=f"fade_{uid}")
    if st.button("Cortar audio", key=f"cut_{uid}"):
        try:
            with st.spinner("Cortando"):
                data = trim_audio(result["data"], ext, start, end, fade)
            base = result["name"].rsplit(".", 1)[0]
            st.session_state.trimmed = {"name": f"{base} (recorte).{ext}", "data": data, "mime": result["mime"]}
        except Exception as e:
            show_error(e, "No se pudo cortar el audio.")
    t = st.session_state.trimmed
    if t:
        st.success(f"{t['name']}  ({len(t['data']) / 1024:.0f} KB)")
        st.download_button("Descargar recorte", data=t["data"], file_name=t["name"], mime=t["mime"],
                           key=f"dl_trim_{uid}")


# ════════════════════════════ MyInstants ════════════════════════════
PLAY_RE = re.compile(
    r"""play\(\s*['"]([^'"]+?\.mp3)['"](?:\s*,\s*['"][^'"]*['"]\s*,\s*['"]([^'"]*)['"])?""")
LINK_RE = re.compile(
    r"""href=["'](?:https?://www\.myinstants\.com)?/(?:[a-z]{2}/)?instant/([^/"'?#]+)/?["'][^>]*>\s*([^<]+?)\s*</a>""")


def mi_abs(path: str) -> str:
    return path if path.startswith("http") else MI_BASE + path


def mi_name_from_file(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0].replace("-", " ").replace("_", " ").strip()


def parse_mi_html(text: str):
    names, order = {}, []
    for slug, name in LINK_RE.findall(text):
        if slug not in names:
            names[slug] = html.unescape(name).strip()
            order.append(slug)
    out, seen = [], set()
    for i, (path, slug) in enumerate(PLAY_RE.findall(text)):
        url = mi_abs(path)
        if url in seen:
            continue
        seen.add(url)
        if not slug and i < len(order):
            slug = order[i]
        out.append({"name": names.get(slug) or mi_name_from_file(path), "slug": slug or url, "sound": url})
    return out


@st.cache_data(ttl=600, show_spinner=False)
def mi_search(query: str):
    results = []
    try:
        r = requests.get(f"{MI_BASE}/es/search/", params={"name": query}, headers=MI_HEADERS, timeout=15)
        r.raise_for_status()
        results = parse_mi_html(r.text)
    except Exception:
        results = []
    if not results:
        r = requests.get(f"{MI_BASE}/api/v1/instants/", params={"name": query, "page": 1},
                         headers=MI_HEADERS, timeout=15)
        r.raise_for_status()
        words = [w for w in query.lower().split() if w]
        for it in r.json().get("results", []):
            name = it.get("name") or ""
            if it.get("sound") and all(w in name.lower() for w in words):
                results.append({"name": name, "slug": it.get("slug") or it["sound"], "sound": mi_abs(it["sound"])})
    return results[:MI_MAX_RESULTS]


@st.cache_data(ttl=600, show_spinner=False)
def mi_from_link(link: str):
    link = link.strip()
    if link.lower().split("?")[0].endswith(".mp3"):
        return [{"name": mi_name_from_file(link), "slug": link, "sound": mi_abs(link)}]
    m = re.search(r"/instant/([^/?#]+)", link)
    if not m:
        raise ValueError("Ese enlace de MyInstants no apunta a un sonido. Abre el sonido y copia su enlace.")
    slug = m.group(1)
    try:
        r = requests.get(f"{MI_BASE}/api/v1/instants/{slug}/", headers=MI_HEADERS, timeout=15)
        r.raise_for_status()
        it = r.json()
        if it.get("sound"):
            return [{"name": it.get("name") or slug, "slug": slug, "sound": mi_abs(it["sound"])}]
    except Exception:
        pass
    url = link if link.startswith("http") else "https://" + link
    r = requests.get(url, headers=MI_HEADERS, timeout=15)
    r.raise_for_status()
    found = parse_mi_html(r.text)
    if not found:
        mp3 = re.search(r"""(/media/sounds/[^"'\s]+?\.mp3)""", r.text)
        if not mp3:
            raise ValueError("No encontré el audio en esa página.")
        found = [{"name": slug.replace("-", " "), "slug": slug, "sound": mi_abs(mp3.group(1))}]
    t = re.search(r"<h1[^>]*>\s*([^<]+?)\s*</h1>", r.text)
    if t:
        found[0]["name"] = html.unescape(t.group(1))
    found[0]["slug"] = slug
    return found[:1]


@st.cache_data(ttl=3600, show_spinner=False, max_entries=64)
def fetch_bytes(url: str) -> bytes:
    r = requests.get(url, headers=MI_HEADERS, timeout=30)
    r.raise_for_status()
    if len(r.content) > 25 * 1024 * 1024:
        raise ValueError("El archivo es demasiado grande.")
    return r.content


def mp3_to_wav(data: bytes) -> bytes:
    if not FFMPEG:
        raise RuntimeError("ffmpeg no disponible")
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in.mp3"), os.path.join(d, "out.wav")
        with open(src, "wb") as fh:
            fh.write(data)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", src, "-ar", "44100", dst],
                       check=True, capture_output=True)
        with open(dst, "rb") as fh:
            return fh.read()


def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "", name).strip()
    return (name or "sonido")[:80]


# ════════════════════════════ Interfaz ════════════════════════════
tab_yt, tab_mi = st.tabs(["YouTube", "Sonidos MyInstants"])

with tab_yt:
    url = st.text_input("Enlace del video", key="yt_url",
                        placeholder="https://youtube.com/watch?v=...  o  https://youtube.com/shorts/...")

    with st.expander("Opciones avanzadas"):
        st.caption("Si YouTube pide verificar que no eres un bot, exporta tus cookies de YouTube "
                   "en formato cookies.txt con una extensión del navegador y súbelas aquí.")
        cookie_up = st.file_uploader("Archivo cookies.txt", type=["txt"], key="cookies")
    cookiefile = None
    if cookie_up is not None:
        cookiefile = os.path.join(tempfile.gettempdir(), f"anghell_cookies_{abs(hash(cookie_up.name))}.txt")
        with open(cookiefile, "wb") as fh:
            fh.write(cookie_up.getvalue())

    info = None
    if url:
        if not YT_REGEX.match(url.strip()):
            st.error("Ese enlace no parece de YouTube. Usa uno de youtube.com, youtu.be o un Short.")
        else:
            try:
                with st.spinner("Leyendo el video"):
                    info = get_info(url.strip(), cookiefile)
                thumb = (f'<img src="{html.escape(info["thumbnail"])}" alt="Miniatura del video">'
                         if info["thumbnail"] else "")
                st.markdown(
                    f'<div class="ac-card">{thumb}<div>'
                    f'<div class="t">{html.escape(info["title"])}</div>'
                    f'<div class="m">{html.escape(info["uploader"])} | {fmt_duration(info["duration"])}'
                    f' | hasta {info["max_height"]}p</div></div></div>',
                    unsafe_allow_html=True,
                )
            except Exception as e:
                show_error(e, "No se pudo leer el video.")

    choice = st.radio("Formato", list(FORMATS.keys()), horizontal=True, index=0, key="yt_fmt")

    if info and FORMATS[choice]["kind"] == "video" and 0 < info["max_height"] < FORMATS[choice]["height"]:
        st.info(f"Este video llega hasta {info['max_height']}p; se descargará en la mejor calidad disponible.")
    if not FFMPEG:
        st.warning("FFmpeg no está disponible. Instálalo para convertir a MP3, WAV o unir video y audio en MP4.")
    if not JS_RUNTIME:
        st.warning("No encontré Deno. YouTube lo exige ahora: ejecuta pip install -r requirements.txt.")

    if st.button("Convertir", disabled=info is None, key="convert"):
        st.session_state.result = None
        st.session_state.trimmed = None
        try:
            st.session_state.result = convert(url.strip(), choice, cookiefile)
        except Exception as e:
            show_error(e, "La conversión falló.")

    if st.session_state.result:
        r = st.session_state.result
        st.success(f"{r['name']}  ({len(r['data']) / (1024 * 1024):.1f} MB)")
        st.download_button("Descargar completo", data=r["data"], file_name=r["name"],
                           mime=r["mime"], key="yt_download")
        if FFMPEG and r["name"].lower().endswith((".mp3", ".wav")):
            audio_trimmer(r)

with tab_mi:
    q = st.text_input("Busca un sonido o pega su enlace", key="mi_q",
                      placeholder="vine boom, bruh, aplausos...  o  https://www.myinstants.com/es/instant/...")
    mi_fmt = st.radio("Formato del sonido", ["MP3", "WAV"], horizontal=True, key="mi_fmt")

    if q.strip():
        mi_failed = False
        try:
            with st.spinner("Buscando sonidos"):
                is_link = "myinstants.com" in q.lower() or q.lower().strip().endswith(".mp3")
                results = mi_from_link(q) if is_link else mi_search(q.strip())
        except Exception as e:
            results, mi_failed = [], True
            show_error(e, "No se pudo consultar MyInstants.")

        if not results and not mi_failed:
            st.info("No hay sonidos con ese nombre. Prueba con otra palabra o pega el enlace del sonido.")

        for i, snd in enumerate(results):
            ext = mi_fmt.lower()
            sid = re.sub(r"[^a-zA-Z0-9]+", "_", snd["slug"])[-60:] + f"_{i}"
            ready_key = f"{snd['sound']}|{ext}"
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 4, 2.3], vertical_alignment="center")
                c1.markdown(f'<div class="ac-sound">{html.escape(snd["name"])}</div>', unsafe_allow_html=True)
                c2.audio(snd["sound"], format="audio/mpeg")
                with c3:
                    ready = st.session_state.sounds.get(ready_key)
                    if ready:
                        st.download_button(f"Guardar {mi_fmt}", data=ready, key=f"mi_dl_{sid}",
                                           file_name=f"{safe_filename(snd['name'])}.{ext}",
                                           mime="audio/mpeg" if ext == "mp3" else "audio/wav")
                    elif st.button("Preparar", key=f"mi_prep_{sid}"):
                        try:
                            data = fetch_bytes(snd["sound"])
                            if ext == "wav":
                                data = mp3_to_wav(data)
                            st.session_state.sounds[ready_key] = data
                            st.rerun()
                        except Exception as e:
                            show_error(e, "No se pudo descargar el sonido.")

st.markdown('<p class="ac-foot">Anghell Convert. Descarga solo contenido propio o con permiso.</p>',
            unsafe_allow_html=True)


# ════════════════════════════ Motor de efectos (lava cartoon + tema) ════════════════════════════
# Se inyecta una sola vez en la página principal; sobrevive a los reruns de Streamlit.
ENGINE_JS = r"""
(function () {
  const D = document, root = D.documentElement;
  if (!root.dataset.acTheme) root.dataset.acTheme = 'dark';
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Lava cartoon: todo se anima con CSS (transform), sin WebGL ---------- */
  const lava = D.createElement('div');
  lava.id = 'ac-lava';
  lava.setAttribute('aria-hidden', 'true');
  lava.innerHTML = "\u003cdiv class=\"ac-surge\">\u003cdiv class=\"ac-level\">\u003cdiv class=\"ac-heat\">\u003c/div>\u003cdiv class=\"ac-lwave back\">\u003csvg viewBox=\"0 0 2880 40\" preserveAspectRatio=\"none\">\u003cpath d=\"M0 20 Q180 0 360 20 T720 20 T1080 20 T1440 20 T1800 20 T2160 20 T2520 20 T2880 20 V40 H0 Z\" fill=\"#ff6a1a\"/>\u003c/svg>\u003c/div>\u003cdiv class=\"ac-body\">\u003ci class=\"ac-bubble\" style=\"left:6%;width:10px;height:10px;animation-duration:7s;animation-delay:-1s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:14%;width:16px;height:16px;animation-duration:9s;animation-delay:-4s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:23%;width:8px;height:8px;animation-duration:6s;animation-delay:-2s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:31%;width:12px;height:12px;animation-duration:8s;animation-delay:-6s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:42%;width:18px;height:18px;animation-duration:10s;animation-delay:-3s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:50%;width:9px;height:9px;animation-duration:7s;animation-delay:-5s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:58%;width:14px;height:14px;animation-duration:9s;animation-delay:-1s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:67%;width:10px;height:10px;animation-duration:6s;animation-delay:-4s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:74%;width:20px;height:20px;animation-duration:11s;animation-delay:-7s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:83%;width:12px;height:12px;animation-duration:8s;animation-delay:-2s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:91%;width:8px;height:8px;animation-duration:7s;animation-delay:-5s\">\u003c/i>\u003ci class=\"ac-bubble\" style=\"left:97%;width:15px;height:15px;animation-duration:9s;animation-delay:-3s\">\u003c/i>\u003c/div>\u003cdiv class=\"ac-lwave\">\u003csvg viewBox=\"0 0 2880 40\" preserveAspectRatio=\"none\">\u003cpath d=\"M0 20 Q180 0 360 20 T720 20 T1080 20 T1440 20 T1800 20 T2160 20 T2520 20 T2880 20 V40 H0 Z\" fill=\"#ffa526\"/>\u003cpath d=\"M0 20 Q180 0 360 20 T720 20 T1080 20 T1440 20 T1800 20 T2160 20 T2520 20 T2880 20\" fill=\"none\" stroke=\"#ffe07a\" stroke-width=\"5\" stroke-linecap=\"round\"/>\u003c/svg>\u003c/div>\u003c/div>\u003c/div>";
  D.body.prepend(lava);
  const surge = lava.querySelector('.ac-surge');

  /* ---------- Botón de tema ---------- */
  const btn = D.createElement('button');
  btn.id = 'ac-theme-toggle'; btn.type = 'button';
  btn.innerHTML = "\u003csvg class=\"ac-ico-sun\" viewBox=\"0 0 24 24\">\u003ccircle cx=\"12\" cy=\"12\" r=\"4.2\"/>\u003cpath d=\"M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6\"/>\u003c/svg>" + "\u003csvg class=\"ac-ico-moon\" viewBox=\"0 0 24 24\">\u003cpath d=\"M20.5 14.6A8.6 8.6 0 0 1 9.4 3.5a8.6 8.6 0 1 0 11.1 11.1z\"/>\u003c/svg>" + "\u003cspan class=\"ac-tlabel\">\u003c/span>";
  D.body.appendChild(btn);
  function syncBtn() {
    const dark = root.dataset.acTheme !== 'light';
    btn.querySelector('.ac-tlabel').textContent = dark ? 'Modo claro' : 'Modo oscuro';
    btn.setAttribute('aria-label', dark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro');
  }
  syncBtn();

  function flipPage() {
    const m = D.querySelector('[data-testid="stMainBlockContainer"]') || D.querySelector('.block-container');
    if (!m) return;
    m.classList.remove('ac-flip'); void m.offsetWidth; m.classList.add('ac-flip');
    const end = e => { if (e.target === m) { m.classList.remove('ac-flip'); m.removeEventListener('animationend', end); } };
    m.addEventListener('animationend', end);
  }

  /* ---------- Cambio de tema: la lava inunda la pantalla y baja ---------- */
  let busy = false;
  btn.addEventListener('click', () => {
    if (busy) return;
    busy = true; btn.classList.add('ac-busy');
    const next = root.dataset.acTheme === 'light' ? 'dark' : 'light';
    const swap = () => { root.dataset.acTheme = next; syncBtn(); flipPage(); };
    if (reduce) { swap(); busy = false; btn.classList.remove('ac-busy'); return; }
    lava.classList.add('ac-flood');
    surge.classList.add('ac-up');
    setTimeout(() => {
      swap();
      setTimeout(() => {
        surge.classList.remove('ac-up');
        setTimeout(() => { lava.classList.remove('ac-flood'); busy = false; btn.classList.remove('ac-busy'); }, 1150);
      }, 250);
    }, 780);
  });
})();
"""

if "unsafe_allow_javascript" in inspect.signature(st.html).parameters:
    # Streamlit reciente: el script corre directo en la página, sin iframe
    st.html(
        '<div class="ac-engine-host"></div><script>'
        "if (!window.__anghellEngine) { window.__anghellEngine = true;" + ENGINE_JS + "}"
        "</script>",
        unsafe_allow_javascript=True,
    )
else:
    # Versiones anteriores: se inyecta desde un componente invisible
    BOOT = (
        '<script type="text/plain" id="ac-engine">' + ENGINE_JS + "</script>"
        """
<script>
(function () {
  try {
    var P = window.parent, D = P.document;
    if (P.__anghellEngine) return;
    P.__anghellEngine = true;
    var s = D.createElement('script');
    s.textContent = document.getElementById('ac-engine').textContent;
    D.head.appendChild(s);
  } catch (e) { console.warn('Anghell engine:', e); }
})();
</script>
"""
    )
    components.html(BOOT, height=0)
