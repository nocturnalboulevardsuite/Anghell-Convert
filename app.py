"""
Anghell Convert
Convertidor de YouTube / Shorts a MP3, WAV o MP4 (4K, 1080p, 720p, 480p).

Efectos:
- Fondo de tierra volcánica renderizado en WebGL.
- Lava que sube muy despacio durante 1 minuto hasta la mitad de la pantalla,
  se queda arriba, se vacía y vuelve a empezar (loop).
- Cambio de tema: la lava inunda la pantalla, cambia el tema y la página
  entra girando como una hoja mientras la lava baja.
"""

import html
import os
import re
import shutil
import tempfile
from urllib.parse import quote

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

if "result" not in st.session_state:
    st.session_state.result = None


def find_ffmpeg():
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


FFMPEG = find_ffmpeg()

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
    "__I_CONVERT__": icon_uri("<path d='M4 12a8 8 0 0 1 13.7-5.6L20 8.5'/><path d='M20 4v4.5h-4.5'/>"
                              "<path d='M20 12a8 8 0 0 1-13.7 5.6L4 15.5'/><path d='M4 20v-4.5h4.5'/>"),
    "__I_DOWNLOAD__": icon_uri("<path d='M12 4v11'/><path d='M7 10.5l5 5 5-5'/><path d='M5 20h14'/>"),
}

# Textura de costra para el logo (ruido fractal generado en SVG)
CRUST = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='320'>"
    "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.024' numOctaves='3' seed='11'/>"
    "<feColorMatrix values='0 0 0 0 0.13  0 0 0 0 0.015  0 0 0 0 0  3.2 0 0 0 -1.55'/></filter>"
    "<rect width='100%' height='100%' filter='url(#n)'/></svg>"
)
ICONS["__CRUST__"] = "url(\"data:image/svg+xml;utf8," + quote(CRUST) + "\")"


# ════════════════════════════ Estilos ════════════════════════════
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Unbounded:wght@500;700;900&family=Manrope:wght@400;500;600;700&display=swap');

:root {
  --bg: #060303;
  --panel: rgba(12, 6, 5, 0.66);
  --pill: rgba(22, 10, 8, 0.72);
  --text: #fbefe6;
  --muted: #b39d92;
  --border: rgba(255, 90, 30, 0.30);
  --input: rgba(8, 4, 3, 0.86);
  --glow: rgba(255, 60, 0, 0.38);
  --lava: linear-gradient(100deg, #6e0800, #ff2a00 18%, #ffb000 32%, #ff4a00 48%,
                          #9a0e00 62%, #ff6a00 78%, #ffd36a 88%, #b81400);
}
:root[data-ac-theme="light"] {
  --bg: #f3e7dc;
  --panel: rgba(255, 249, 243, 0.76);
  --pill: rgba(255, 255, 255, 0.78);
  --text: #1c0a04;
  --muted: #6e4f40;
  --border: rgba(200, 60, 10, 0.32);
  --input: rgba(255, 255, 255, 0.94);
  --glow: rgba(255, 90, 20, 0.25);
}

html, body { background: var(--bg) !important; }
.stApp, .stApp p, .stApp label, .stApp span, .stApp div, .stApp input, .stApp button {
  font-family: 'Manrope', system-ui, sans-serif;
}
.stApp { background: transparent !important; color: var(--text); position: relative; z-index: 1; }
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }

/* Lienzo de lava (WebGL) */
#ac-lava { position: fixed; inset: 0; width: 100vw; height: 100vh; z-index: 0;
           pointer-events: none; display: block; }
#ac-lava-fallback { position: fixed; left: 0; right: 0; bottom: 0; height: 2vh; z-index: 0;
  pointer-events: none;
  background: linear-gradient(to top, #4a0400, #c42200 55%, #ff8a10 92%, #ffd27a);
  box-shadow: 0 -30px 80px rgba(255, 80, 0, .45);
  animation: ac-fb-rise 100s ease-in-out infinite; }
@keyframes ac-fb-rise { 0% { height: 2vh } 60% { height: 50vh } 72% { height: 50vh }
                        96% { height: 2vh } 100% { height: 2vh } }

/* Componente invisible que arranca el motor */
div[data-testid="stElementContainer"]:has(iframe),
.element-container:has(iframe) { display: none !important; }

/* Panel de vidrio que gira como una página */
[data-testid="stMain"], section.main { perspective: 1800px; }
.block-container, [data-testid="stMainBlockContainer"] {
  max-width: 760px;
  margin-top: 4.5rem; margin-bottom: 4rem;
  padding: 2.2rem 2.2rem 1.6rem !important;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 26px;
  backdrop-filter: blur(14px) saturate(1.2);
  -webkit-backdrop-filter: blur(14px) saturate(1.2);
  box-shadow: 0 30px 80px rgba(0, 0, 0, .35), 0 0 0 1px rgba(255, 120, 40, .05) inset;
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
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
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
.ac-hero { text-align: center; margin-bottom: 1.4rem; }
.ac-emblem { display: inline-block; animation: ac-pulse 3.2s ease-in-out infinite; }
.ac-emblem svg { width: 92px; height: 92px; display: block; }
@keyframes ac-pulse {
  0%, 100% { filter: drop-shadow(0 0 10px rgba(255, 70, 0, .55)); }
  50%      { filter: drop-shadow(0 0 26px rgba(255, 120, 0, .85)); }
}
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
  animation: ac-molten 14s linear infinite;
  filter: drop-shadow(0 0 10px rgba(255, 70, 0, .55)) drop-shadow(0 2px 0 rgba(60, 4, 0, .6));
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
                     64% { opacity: 1 } 100% { opacity: 0; transform: translateY(80px) scale(.6) } }
.ac-sub { color: var(--muted) !important; font-size: 1.02rem; margin: 1.1rem auto 0; max-width: 46ch; }

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

div[role="radiogroup"] { gap: .55rem; flex-wrap: wrap; }
div[role="radiogroup"] > label {
  display: inline-flex !important; align-items: center;
  background: var(--pill); border: 1px solid var(--border); border-radius: 999px;
  padding: .5rem 1rem !important; margin: 0 !important;
  transition: border-color .2s, box-shadow .2s, transform .2s; cursor: pointer;
}
div[role="radiogroup"] > label:hover { transform: translateY(-1px); }
div[role="radiogroup"] > label > div:first-child { display: none; }
div[role="radiogroup"] > label p { color: var(--text) !important; font-weight: 600; }
div[role="radiogroup"] > label::before {
  content: ""; width: 17px; height: 17px; margin-right: .5rem; flex-shrink: 0;
  background: var(--muted);
  -webkit-mask: __I_FILM__ center / contain no-repeat; mask: __I_FILM__ center / contain no-repeat;
}
div[role="radiogroup"] > label:nth-child(1)::before {
  -webkit-mask-image: __I_NOTE__; mask-image: __I_NOTE__; }
div[role="radiogroup"] > label:nth-child(2)::before {
  -webkit-mask-image: __I_WAVE__; mask-image: __I_WAVE__; }
div[role="radiogroup"] > label:has(input:checked) {
  border-color: #ff4d00; box-shadow: 0 0 18px var(--glow), inset 0 0 12px rgba(255, 80, 0, .12); }
div[role="radiogroup"] > label:has(input:checked)::before { background: #ff5a00; }

.stButton > button, .stDownloadButton > button {
  width: 100%; border: none !important; border-radius: 14px !important;
  padding: .85rem 1rem !important; color: #fff !important;
  background: var(--lava) !important; background-size: 320% 100% !important;
  animation: ac-btnflow 9s linear infinite;
  box-shadow: 0 8px 28px var(--glow); transition: transform .15s, box-shadow .2s;
}
.stButton > button p, .stDownloadButton > button p {
  font-family: 'Unbounded', sans-serif !important; font-weight: 700; color: #fff !important;
  text-shadow: 0 1px 2px rgba(60, 4, 0, .6); }
.stButton > button::before, .stDownloadButton > button::before {
  content: ""; width: 18px; height: 18px; margin-right: .55rem; background: #fff;
  -webkit-mask: __I_CONVERT__ center / contain no-repeat; mask: __I_CONVERT__ center / contain no-repeat; }
.stDownloadButton > button::before { -webkit-mask-image: __I_DOWNLOAD__; mask-image: __I_DOWNLOAD__; }
.stButton > button:hover, .stDownloadButton > button:hover {
  transform: translateY(-2px); box-shadow: 0 12px 36px var(--glow); }
.stButton > button:disabled { filter: grayscale(.7) brightness(.8); opacity: .6; }
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible {
  outline: 2px solid #ff9a00 !important; outline-offset: 3px; }
@keyframes ac-btnflow { to { background-position: 320% 50%; } }

.ac-card {
  display: flex; gap: 1rem; align-items: center;
  background: var(--pill); border: 1px solid var(--border); border-radius: 18px;
  padding: .9rem; margin: .9rem 0 1.2rem; animation: ac-in .5s ease-out both;
}
@keyframes ac-in { from { opacity: 0; transform: translateY(6px); } }
.ac-card img { width: 168px; border-radius: 12px; flex-shrink: 0; }
.ac-card .t { font-weight: 700; color: var(--text); line-height: 1.3; }
.ac-card .m { color: var(--muted); font-size: .9rem; margin-top: .35rem; }

.stProgress > div > div > div > div,
[data-testid="stProgress"] [role="progressbar"] > div > div {
  background: var(--lava) !important; background-size: 320% 100% !important;
  animation: ac-btnflow 3s linear infinite; }

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
  <p class="ac-sub">Pega un enlace de YouTube o Shorts y elige el formato.</p>
</div>
"""
st.markdown(LOGO, unsafe_allow_html=True)


# ════════════════════════════ Lógica de descarga ════════════════════════════
@st.cache_data(ttl=900, show_spinner=False)
def get_info(url: str) -> dict:
    with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    heights = sorted({f.get("height") for f in info.get("formats", []) if f.get("height")})
    return {
        "title": info.get("title", "Sin título"),
        "uploader": info.get("uploader", ""),
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("thumbnail"),
        "max_height": heights[-1] if heights else 0,
    }


def fmt_duration(sec: int) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_options(choice: str, outdir: str, hook) -> dict:
    cfg = FORMATS[choice]
    opts = {
        "outtmpl": os.path.join(outdir, "%(title).90s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    if FFMPEG:
        opts["ffmpeg_location"] = FFMPEG

    if cfg["kind"] == "audio":
        pp = {"key": "FFmpegExtractAudio", "preferredcodec": cfg["ext"]}
        if cfg["ext"] == "mp3":
            pp["preferredquality"] = "320"
        opts.update({"format": "bestaudio/best", "postprocessors": [pp]})
    else:
        h = cfg["height"]
        opts.update({
            "format": (f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
                       f"bv*[height<={h}]+ba/b[height<={h}]/b"),
            "merge_output_format": "mp4",
        })
    return opts


def convert(url: str, choice: str):
    outdir = tempfile.mkdtemp(prefix="anghell_")
    bar = st.progress(0, text="Preparando")

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            pct = min(done / total, 1.0) if total else 0
            bar.progress(pct, text=f"Descargando {pct * 100:.0f}%")
        elif d["status"] == "finished":
            bar.progress(1.0, text="Convirtiendo con FFmpeg")

    try:
        with yt_dlp.YoutubeDL(build_options(choice, outdir, hook)) as ydl:
            ydl.download([url])

        ext = FORMATS[choice]["ext"]
        files = [f for f in os.listdir(outdir) if f.lower().endswith("." + ext)]
        if not files:
            raise RuntimeError("No se generó el archivo final. Revisa que FFmpeg esté instalado.")
        path = max((os.path.join(outdir, f) for f in files), key=os.path.getsize)
        with open(path, "rb") as fh:
            data = fh.read()
        bar.progress(1.0, text="Listo")
        return {"name": os.path.basename(path), "data": data, "mime": FORMATS[choice]["mime"]}
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


# ════════════════════════════ Interfaz ════════════════════════════
url = st.text_input("Enlace del video",
                    placeholder="https://youtube.com/watch?v=...  o  https://youtube.com/shorts/...")

info = None
if url:
    if not YT_REGEX.match(url.strip()):
        st.error("Ese enlace no parece de YouTube. Usa uno de youtube.com, youtu.be o un Short.")
    else:
        try:
            with st.spinner("Leyendo el video"):
                info = get_info(url.strip())
            thumb = (f'<img src="{html.escape(info["thumbnail"])}" alt="Miniatura del video">'
                     if info["thumbnail"] else "")
            st.markdown(
                f'<div class="ac-card">{thumb}<div>'
                f'<div class="t">{html.escape(info["title"])}</div>'
                f'<div class="m">{html.escape(info["uploader"] or "")} | {fmt_duration(info["duration"])}'
                f' | hasta {info["max_height"]}p</div></div></div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.error(f"No se pudo leer el video: {e}")

choice = st.radio("Formato", list(FORMATS.keys()), horizontal=True, index=0)

if info and FORMATS[choice]["kind"] == "video" and info["max_height"] < FORMATS[choice]["height"]:
    st.info(f"Este video llega hasta {info['max_height']}p; se descargará en la mejor calidad disponible.")

if not FFMPEG:
    st.warning("FFmpeg no está disponible. Instálalo para convertir a MP3, WAV o unir video y audio en MP4.")

if st.button("Convertir", disabled=info is None):
    st.session_state.result = None
    try:
        st.session_state.result = convert(url.strip(), choice)
    except Exception as e:
        st.error(f"La conversión falló: {e}")

if st.session_state.result:
    r = st.session_state.result
    st.success(f"{r['name']}  ({len(r['data']) / (1024 * 1024):.1f} MB)")
    st.download_button("Descargar archivo", data=r["data"], file_name=r["name"], mime=r["mime"])

st.markdown('<p class="ac-foot">Anghell Convert. Descarga solo contenido propio o con permiso.</p>',
            unsafe_allow_html=True)


# ════════════════════════════ Motor de lava (WebGL) ════════════════════════════
# Se inyecta una sola vez en la página principal; sobrevive a los reruns de Streamlit.
ENGINE_JS = r"""
(function () {
  const D = document, root = D.documentElement;
  if (!root.dataset.acTheme) root.dataset.acTheme = 'dark';

  /* ---------- Botón de tema con íconos dibujados ---------- */
  const SUN = '<svg class="ac-ico-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.2"/>' +
    '<path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6' +
    'M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></svg>';
  const MOON = '<svg class="ac-ico-moon" viewBox="0 0 24 24">' +
    '<path d="M20.5 14.6A8.6 8.6 0 0 1 9.4 3.5a8.6 8.6 0 1 0 11.1 11.1z"/></svg>';
  const btn = D.createElement('button');
  btn.id = 'ac-theme-toggle'; btn.type = 'button';
  btn.innerHTML = SUN + MOON + '<span class="ac-tlabel"></span>';
  D.body.appendChild(btn);
  function syncBtn() {
    const dark = root.dataset.acTheme !== 'light';
    btn.querySelector('.ac-tlabel').textContent = dark ? 'Modo claro' : 'Modo oscuro';
    btn.setAttribute('aria-label', dark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro');
  }
  syncBtn();

  /* ---------- Estado ---------- */
  let burst = 0;
  let theme = root.dataset.acTheme === 'light' ? 1 : 0;
  const START = performance.now();
  const RISE = 60, HOLD = 12, DRAIN = 24, REST = 4, CYCLE = RISE + HOLD + DRAIN + REST;
  const BASE = 0.02, TOP = 0.5;
  const ss = x => x * x * (3 - 2 * x);
  function levelAt(t) {
    const c = t % CYCLE; let k;
    if (c < RISE) k = ss(c / RISE);                       // sube muy de a poco durante 60 s
    else if (c < RISE + HOLD) k = 1;                      // se queda en la mitad
    else if (c < RISE + HOLD + DRAIN) k = 1 - ss((c - RISE - HOLD) / DRAIN); // se vacía
    else k = 0;
    return BASE + (TOP - BASE) * k;
  }

  /* ---------- Shader de lava y tierra ---------- */
  const FS = `
precision highp float;
uniform vec2 uRes;
uniform float uTime;
uniform float uLevel;
uniform float uTheme;
uniform float uBurst;

float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
vec2 hash2(vec2 p){
  return fract(sin(vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)))) * 43758.5453);
}
float noise(vec2 p){
  vec2 i = floor(p); vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p){
  float v = 0.0; float a = 0.5;
  mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 5; i++){ v += a * noise(p); p = m * p; a *= 0.5; }
  return v;
}
vec2 voronoi(vec2 p, float tt){
  vec2 n = floor(p); vec2 f = fract(p);
  float d1 = 8.0; float d2 = 8.0;
  for (int j = -1; j <= 1; j++){
    for (int i = -1; i <= 1; i++){
      vec2 g = vec2(float(i), float(j));
      vec2 o = hash2(n + g);
      o = 0.5 + 0.4 * sin(tt + 6.2831 * o);
      vec2 r = g + o - f;
      float d = dot(r, r);
      if (d < d1){ d2 = d1; d1 = d; } else if (d < d2){ d2 = d; }
    }
  }
  return vec2(sqrt(d1), sqrt(d2));
}
vec3 lavaRamp(float h){
  h = clamp(h, 0.0, 1.0);
  vec3 c = mix(vec3(0.05, 0.010, 0.008), vec3(0.42, 0.030, 0.0), smoothstep(0.0, 0.30, h));
  c = mix(c, vec3(0.95, 0.20, 0.02), smoothstep(0.30, 0.60, h));
  c = mix(c, vec3(1.00, 0.60, 0.12), smoothstep(0.60, 0.85, h));
  c = mix(c, vec3(1.00, 0.93, 0.62), smoothstep(0.85, 1.00, h));
  return c;
}

void main(){
  vec2 uv = gl_FragCoord.xy / uRes;
  float asp = uRes.x / uRes.y;
  vec2 p = vec2(uv.x * asp, uv.y);
  float t = uTime;

  float L = mix(uLevel, 1.32, uBurst);
  float amp = (0.010 + 0.040 * uBurst) * smoothstep(0.0, 0.05, L);
  float wave = sin(p.x * 5.0 + t * 0.9) * 0.6 + sin(p.x * 11.0 - t * 1.3) * 0.25
             + (fbm(vec2(p.x * 2.5, t * 0.25)) - 0.5) * 1.6;
  float surf = L + amp * wave;
  float dy = uv.y - surf;
  float on = smoothstep(0.0, 0.04, L);

  vec3 col;
  if (dy > 0.0){
    /* ---- Tierra volcánica ---- */
    vec2 ep = p * 3.0;
    float e1 = fbm(ep * 1.2);
    float e2 = fbm(ep * 4.5 + 7.3);
    float strata = 0.5 + 0.5 * sin(p.y * 26.0 + fbm(ep * 0.7) * 7.0);
    vec2 vc = voronoi(p * 6.0 + fbm(p * 3.0) * 1.5 + 3.0, 0.0);
    float crack = 1.0 - smoothstep(0.0, 0.06, vc.y - vc.x);
    vec3 darkE = mix(vec3(0.030, 0.024, 0.022), vec3(0.105, 0.072, 0.058), e1) * (0.75 + 0.5 * e2)
               + strata * 0.012;
    vec3 lightE = mix(vec3(0.78, 0.67, 0.57), vec3(0.94, 0.88, 0.80), e1) * (0.93 + 0.10 * e2)
               - strata * 0.025;
    vec3 earth = mix(darkE, lightE, uTheme);
    earth *= 1.0 - crack * mix(0.55, 0.22, uTheme);

    float heat = exp(-dy * 7.0) * on;
    earth += crack * vec3(1.0, 0.32, 0.04) * pow(heat, 1.5) * 1.4 * (1.0 - 0.5 * uTheme);
    float glow = exp(-dy * 16.0) * on;
    earth = mix(earth, vec3(1.0, 0.36, 0.05), clamp(glow * 0.6, 0.0, 1.0));
    earth += vec3(0.5, 0.08, 0.0) * heat * 0.18 * (1.0 - uTheme);

    /* ---- Brasas que suben ---- */
    float emb = 0.0;
    for (int i = 0; i < 3; i++){
      float fi = float(i);
      float sc = 16.0 + fi * 10.0;
      vec2 q = vec2(p.x * sc + fi * 7.0, (dy - t * (0.035 + 0.02 * fi)) * sc);
      vec2 id = floor(q); vec2 f = fract(q) - 0.5;
      float rnd = hash(id + fi * 13.1);
      if (rnd > 0.88 - 0.08 * uBurst){
        vec2 o = (hash2(id) - 0.5) * 0.6;
        o.x += 0.25 * sin(t * 1.7 + rnd * 40.0);
        float d = length(f - o);
        float life = 1.0 - smoothstep(0.0, 0.28 + 0.3 * uBurst, dy);
        emb += (1.0 - smoothstep(0.0, 0.11, d)) * life * (0.6 + 0.4 * sin(t * 7.0 + rnd * 60.0));
      }
    }
    col = mix(earth, vec3(1.0, 0.58, 0.16), clamp(emb, 0.0, 1.0) * on);

    float vig = smoothstep(0.35, 1.25, length((uv - 0.5) * vec2(asp, 1.0)));
    col *= 1.0 - vig * 0.45 * (1.0 - uTheme);
  } else {
    /* ---- Lava: flujo con distorsión, costra y grietas incandescentes ---- */
    float depth = -dy;
    vec2 lp = p * 3.0 + vec2(t * 0.035, -t * 0.012);
    vec2 w = vec2(fbm(lp + t * 0.05), fbm(lp + vec2(5.2, 1.3) - t * 0.04));
    float n = fbm(lp + 2.2 * w);
    vec2 v = voronoi(lp * 1.7 + w * 1.4, t * 0.18);
    float edge = v.y - v.x;
    float cracks = 1.0 - smoothstep(0.0, 0.10 + 0.08 * n, edge);
    float crust = smoothstep(0.38, 0.72, n) * (1.0 - cracks);
    float h = 0.52 + 0.5 * cracks + 0.3 * (n - 0.5) - 0.6 * crust;
    h += 0.07 * sin(t * 1.3 + n * 14.0);
    h -= depth * 0.22;
    col = lavaRamp(h);

    float rim = exp(-depth * 55.0);
    col = mix(col, vec3(1.0, 0.78, 0.35), rim * 0.75);

    vec2 bq = vec2(p.x * 8.0, (uv.y - t * 0.03) * 8.0);
    vec2 bid = floor(bq); vec2 bf = fract(bq) - 0.5;
    float br = hash(bid);
    if (br > 0.82){
      vec2 bo = (hash2(bid) - 0.5) * 0.5;
      float rr = 0.08 + 0.1 * hash(bid + 3.7);
      float bd = length(bf - bo);
      float ring = (1.0 - smoothstep(rr - 0.03, rr, bd)) - (1.0 - smoothstep(rr - 0.08, rr - 0.04, bd));
      col += vec3(1.0, 0.7, 0.25) * max(ring, 0.0) * 0.35 * (1.0 - smoothstep(0.0, 0.4, depth));
    }
    col += vec3(1.0, 0.4, 0.1) * uBurst * 0.06;
  }
  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}`;

  /* ---------- WebGL ---------- */
  const cv = D.createElement('canvas');
  cv.id = 'ac-lava';
  D.body.prepend(cv);
  let draw = null;
  try {
    const gl = cv.getContext('webgl', { antialias: false, depth: false, stencil: false,
                                         powerPreference: 'high-performance' });
    if (gl) draw = setup(gl);
  } catch (e) { console.warn('Anghell WebGL:', e); }
  if (!draw) {
    cv.remove();
    const f = D.createElement('div'); f.id = 'ac-lava-fallback'; D.body.prepend(f);
  }

  function setup(gl) {
    const VS = 'attribute vec2 a; void main(){ gl_Position = vec4(a, 0.0, 1.0); }';
    function sh(type, src) {
      const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    }
    const pr = gl.createProgram();
    gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS));
    gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(pr);
    if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
    gl.useProgram(pr);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(pr, 'a');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const U = n => gl.getUniformLocation(pr, n);
    const uRes = U('uRes'), uTime = U('uTime'), uLevel = U('uLevel'),
          uTheme = U('uTheme'), uBurst = U('uBurst');

    // Calidad adaptativa: baja la resolución interna si el equipo va lento
    let Q = innerWidth < 700 ? 0.5 : 0.62, slow = 0, last = 0;
    function resize() {
      const w = Math.max(2, Math.round(innerWidth * Q)), h = Math.max(2, Math.round(innerHeight * Q));
      if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; gl.viewport(0, 0, w, h); }
    }
    return function (now, t, level) {
      if (last) {
        slow = (now - last) > 30 ? slow + 1 : Math.max(0, slow - 1);
        if (slow > 90 && Q > 0.35) { Q -= 0.08; slow = 0; }
      }
      last = now;
      resize();
      gl.uniform2f(uRes, cv.width, cv.height);
      gl.uniform1f(uTime, t % 3600);
      gl.uniform1f(uLevel, level);
      gl.uniform1f(uTheme, theme);
      gl.uniform1f(uBurst, burst);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
  }

  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  function loop(now) {
    const t = (now - START) / 1000;
    if (draw) draw(now, reduce ? t * 0.3 : t, levelAt(t));
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  /* ---------- Transición de tema: inundación de lava + giro de página ---------- */
  function tween(from, to, ms, ease, set, done) {
    const s = performance.now();
    (function step(n) {
      const k = Math.min(1, (n - s) / ms);
      set(from + (to - from) * ease(k));
      if (k < 1) requestAnimationFrame(step); else if (done) done();
    })(s);
  }
  const easeIn = k => k * k * k;
  const easeOut = k => 1 - Math.pow(1 - k, 3);

  function flipPage() {
    const m = D.querySelector('[data-testid="stMainBlockContainer"]') || D.querySelector('.block-container');
    if (!m) return;
    m.classList.remove('ac-flip'); void m.offsetWidth; m.classList.add('ac-flip');
    const end = e => { if (e.target === m) { m.classList.remove('ac-flip'); m.removeEventListener('animationend', end); } };
    m.addEventListener('animationend', end);
  }

  let busy = false;
  btn.addEventListener('click', () => {
    if (busy) return;
    busy = true; btn.classList.add('ac-busy');
    const next = root.dataset.acTheme === 'light' ? 'dark' : 'light';
    const swap = () => { root.dataset.acTheme = next; theme = next === 'light' ? 1 : 0; syncBtn(); flipPage(); };
    const finish = () => { cv.style.zIndex = ''; busy = false; btn.classList.remove('ac-busy'); };
    if (!draw || reduce) { swap(); finish(); return; }
    cv.style.zIndex = '999990';                               // la lava pasa por encima de todo
    tween(0, 1, 850, easeIn, v => burst = v, () => {          // erupción: cubre la pantalla
      swap();                                                 // cambio de tema oculto bajo la lava
      setTimeout(() => tween(1, 0, 1300, easeOut, v => burst = v, finish), 260);  // la lava baja
    });
  });
})();
"""

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
