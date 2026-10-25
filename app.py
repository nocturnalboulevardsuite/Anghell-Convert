"""
Anghell Convert
Convertidor de videos de YouTube / Shorts a MP3, WAV o MP4 (4K, 1080p, 720p, 480p).
"""

import os
import re
import shutil
import tempfile

import streamlit as st
import yt_dlp

# ───────────────────────── Configuración base ─────────────────────────
st.set_page_config(page_title="Anghell Convert", page_icon="🔥", layout="centered")

if "theme" not in st.session_state:
    st.session_state.theme = "dark"  # tema por defecto
if "result" not in st.session_state:
    st.session_state.result = None


def find_ffmpeg():
    """Usa el ffmpeg del sistema; si no existe, el binario de imageio-ffmpeg."""
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

# ───────────────────────── Paletas de tema ─────────────────────────
PALETTES = {
    "dark": {
        "bg": "#050304",
        "bg2": "#140806",
        "surface": "rgba(22, 12, 10, 0.78)",
        "text": "#fbefe6",
        "muted": "#a8948a",
        "border": "rgba(255, 90, 30, 0.28)",
        "input": "#0d0706",
        "glow": "rgba(255, 60, 0, 0.35)",
    },
    "light": {
        "bg": "#fff8f3",
        "bg2": "#ffe6d6",
        "surface": "rgba(255, 255, 255, 0.85)",
        "text": "#1c0a04",
        "muted": "#7a5a4a",
        "border": "rgba(220, 60, 10, 0.30)",
        "input": "#ffffff",
        "glow": "rgba(255, 90, 20, 0.22)",
    },
}
p = PALETTES[st.session_state.theme]

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Unbounded:wght@600;800&family=Manrope:wght@400;500;700&display=swap');

:root {{
  --bg: {p['bg']};
  --bg2: {p['bg2']};
  --surface: {p['surface']};
  --text: {p['text']};
  --muted: {p['muted']};
  --border: {p['border']};
  --input: {p['input']};
  --glow: {p['glow']};
  --rgbic: linear-gradient(90deg, #ff0f1f, #ff4d00, #ff9a00, #ff2a00, #2a0000, #ff0f1f);
}}

@keyframes rgbic-flow {{
  0%   {{ background-position: 0% 50%; }}
  100% {{ background-position: 300% 50%; }}
}}

html, body, [class*="css"], .stApp, .stMarkdown, p, label, span, div {{
  font-family: 'Manrope', system-ui, sans-serif;
}}

.stApp {{
  background:
    radial-gradient(1200px 500px at 50% -10%, var(--bg2), transparent 70%),
    var(--bg);
  color: var(--text);
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbar"] {{ display: none; }}
.block-container {{ padding-top: 2.2rem; max-width: 760px; }}

/* Título RGBIC animado */
.ac-title {{
  font-family: 'Unbounded', sans-serif;
  font-weight: 800;
  font-size: clamp(2.3rem, 7vw, 3.8rem);
  line-height: 1.05;
  letter-spacing: -0.02em;
  background: var(--rgbic);
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: rgbic-flow 6s linear infinite;
  margin: 0;
}}
.ac-sub {{ color: var(--muted); font-size: 1.02rem; margin: .4rem 0 1.6rem; }}

/* Barra RGBIC bajo el título */
.ac-strip {{
  height: 3px; border-radius: 3px; margin-bottom: 1.8rem;
  background: var(--rgbic); background-size: 300% 100%;
  animation: rgbic-flow 6s linear infinite;
  box-shadow: 0 0 18px var(--glow);
}}

/* Textos */
.stApp h1, .stApp h2, .stApp h3, .stApp label, .stApp p {{ color: var(--text); }}
[data-testid="stWidgetLabel"] p {{ color: var(--muted) !important; font-weight: 500; }}

/* Input */
.stTextInput input {{
  background: var(--input) !important;
  color: var(--text) !important;
  border: 1px solid var(--border) !important;
  border-radius: 12px !important;
  padding: .85rem 1rem !important;
  font-size: 1rem !important;
}}
.stTextInput input:focus {{
  border-color: #ff5a1f !important;
  box-shadow: 0 0 0 3px var(--glow) !important;
}}

/* Radio de formatos como pastillas */
div[role="radiogroup"] {{ gap: .5rem; flex-wrap: wrap; }}
div[role="radiogroup"] > label {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: .45rem 1rem !important;
  transition: border-color .2s, box-shadow .2s;
}}
div[role="radiogroup"] > label:has(input:checked) {{
  border-color: #ff4d00;
  box-shadow: 0 0 14px var(--glow);
}}
div[role="radiogroup"] > label > div:first-child {{ display: none; }}

/* Botones */
.stButton > button, .stDownloadButton > button {{
  width: 100%;
  border: none !important;
  border-radius: 12px !important;
  padding: .8rem 1rem !important;
  font-family: 'Unbounded', sans-serif !important;
  font-weight: 600 !important;
  color: #fff !important;
  background: var(--rgbic) !important;
  background-size: 300% 100% !important;
  animation: rgbic-flow 8s linear infinite;
  box-shadow: 0 6px 24px var(--glow);
  transition: transform .15s;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{ transform: translateY(-1px); }}
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible {{
  outline: 2px solid #ff9a00 !important; outline-offset: 2px;
}}

/* Botón de tema (pequeño, discreto) */
.ac-theme .stButton > button {{
  width: auto; padding: .4rem .8rem !important;
  background: var(--surface) !important; color: var(--text) !important;
  border: 1px solid var(--border) !important; animation: none; box-shadow: none;
  font-family: 'Manrope', sans-serif !important;
}}

/* Tarjeta de preview */
.ac-card {{
  display: flex; gap: 1rem; align-items: center;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; padding: .9rem; margin: 1rem 0 1.2rem;
  backdrop-filter: blur(8px);
}}
.ac-card img {{ width: 160px; border-radius: 10px; flex-shrink: 0; }}
.ac-card .t {{ font-weight: 700; color: var(--text); line-height: 1.3; }}
.ac-card .m {{ color: var(--muted); font-size: .9rem; margin-top: .3rem; }}

/* Barra de progreso */
.stProgress > div > div > div > div {{
  background: var(--rgbic) !important; background-size: 300% 100% !important;
  animation: rgbic-flow 3s linear infinite;
}}

.ac-foot {{ color: var(--muted); font-size: .8rem; text-align: center; margin-top: 3rem; }}

@media (max-width: 560px) {{
  .ac-card {{ flex-direction: column; align-items: flex-start; }}
  .ac-card img {{ width: 100%; }}
}}
@media (prefers-reduced-motion: reduce) {{
  * {{ animation: none !important; }}
}}
</style>
""",
    unsafe_allow_html=True,
)

# ───────────────────────── Encabezado + toggle de tema ─────────────────────────
col_title, col_theme = st.columns([5, 1.3])
with col_title:
    st.markdown('<h1 class="ac-title">Anghell Convert</h1>', unsafe_allow_html=True)
with col_theme:
    st.markdown('<div class="ac-theme">', unsafe_allow_html=True)
    label = "☀️ Claro" if st.session_state.theme == "dark" else "🌙 Oscuro"
    if st.button(label, key="theme_btn"):
        st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    '<p class="ac-sub">Pega un enlace de YouTube o Shorts y descárgalo en el formato que quieras.</p>'
    '<div class="ac-strip"></div>',
    unsafe_allow_html=True,
)

# ───────────────────────── Lógica ─────────────────────────
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
            "format": (
                f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
                f"bv*[height<={h}]+ba/"
                f"b[height<={h}]/b"
            ),
            "merge_output_format": "mp4",
        })
    return opts


def convert(url: str, choice: str):
    outdir = tempfile.mkdtemp(prefix="anghell_")
    bar = st.progress(0, text="Preparando…")

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            pct = min(done / total, 1.0) if total else 0
            bar.progress(pct, text=f"Descargando… {pct*100:.0f}%")
        elif d["status"] == "finished":
            bar.progress(1.0, text="Convirtiendo con FFmpeg…")

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


# ───────────────────────── Interfaz ─────────────────────────
url = st.text_input("Enlace del video", placeholder="https://youtube.com/watch?v=…  o  https://youtube.com/shorts/…")

info = None
if url:
    if not YT_REGEX.match(url.strip()):
        st.error("Ese enlace no parece de YouTube. Usa uno de youtube.com, youtu.be o un Short.")
    else:
        try:
            with st.spinner("Leyendo el video…"):
                info = get_info(url.strip())
            thumb = f'<img src="{info["thumbnail"]}" alt="Miniatura">' if info["thumbnail"] else ""
            st.markdown(
                f'<div class="ac-card">{thumb}<div>'
                f'<div class="t">{info["title"]}</div>'
                f'<div class="m">{info["uploader"]}  |  {fmt_duration(info["duration"])}'
                f'  |  hasta {info["max_height"]}p</div></div></div>',
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
    size_mb = len(r["data"]) / (1024 * 1024)
    st.success(f"{r['name']}  ({size_mb:.1f} MB)")
    st.download_button("Descargar archivo", data=r["data"], file_name=r["name"], mime=r["mime"])

st.markdown(
    '<p class="ac-foot">Anghell Convert — usa solo contenido propio o con permiso para descargar.</p>',
    unsafe_allow_html=True,
)
