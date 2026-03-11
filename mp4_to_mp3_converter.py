import streamlit as st
import os
import sys
import tempfile
import shutil
import math
import gc
import subprocess
from pathlib import Path
from moviepy import VideoFileClip
from moviepy.audio.AudioClip import concatenate_audioclips
import imageio_ffmpeg


def get_downloads_dir() -> Path:
    """取得系統預設下載目錄（Windows 讀取 Registry，其他平台用 ~/Downloads）。"""
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            )
            downloads, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            winreg.CloseKey(key)
            return Path(downloads)
        except Exception:
            pass
    return Path.home() / "Downloads"

# ── ffmpeg 路徑（使用 imageio_ffmpeg 內建的二進位檔）──────────────
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

# ── 支援的格式 ─────────────────────────────────────────────────
VIDEO_EXTENSIONS = ["mp4"]
AUDIO_EXTENSIONS = ["mp3", "wav", "m4a", "ogg", "flac", "aac", "wma"]
ALL_EXTENSIONS   = VIDEO_EXTENSIONS + AUDIO_EXTENSIONS

# ── 常數 ──────────────────────────────────────────────────────
LARGE_FILE_THRESHOLD_MB = 200          # 超過此大小自動分段
SEGMENT_DURATION_SEC    = 10 * 60      # 每段 10 分鐘

# ── 頁面設定 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="音訊 / 影片 轉 MP3 轉換器",
    page_icon="🎵",
    layout="centered",
)

# ── 自訂 CSS ──────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .main {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        min-height: 100vh;
    }

    .stApp {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    }

    .hero-card {
        background: rgba(255, 255, 255, 0.07);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 20px;
        padding: 2.5rem 2rem;
        text-align: center;
        backdrop-filter: blur(12px);
        margin-bottom: 1.5rem;
    }

    .hero-title {
        font-size: 2.4rem;
        font-weight: 700;
        background: linear-gradient(90deg, #a78bfa, #60a5fa, #34d399);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.3rem;
    }

    .hero-subtitle {
        color: rgba(255,255,255,0.55);
        font-size: 1rem;
        margin-top: 0;
    }

    .info-box {
        background: rgba(99, 102, 241, 0.15);
        border-left: 4px solid #818cf8;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        color: rgba(255,255,255,0.75);
        font-size: 0.9rem;
        margin-bottom: 1rem;
    }

    .warn-box {
        background: rgba(251, 191, 36, 0.12);
        border-left: 4px solid #fbbf24;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        color: rgba(255,255,255,0.80);
        font-size: 0.9rem;
        margin-bottom: 1rem;
    }

    .stButton > button {
        width: 100%;
        background: linear-gradient(90deg, #7c3aed, #2563eb);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 0.75rem 2rem;
        font-size: 1.05rem;
        font-weight: 600;
        transition: opacity 0.2s ease;
        cursor: pointer;
    }

    .stButton > button:hover {
        opacity: 0.88;
    }

    .stProgress > div > div {
        background: linear-gradient(90deg, #7c3aed, #2563eb);
        border-radius: 10px;
    }

    .success-box {
        background: rgba(52, 211, 153, 0.15);
        border: 1px solid rgba(52, 211, 153, 0.4);
        border-radius: 12px;
        padding: 1rem 1.2rem;
        color: #6ee7b7;
        text-align: center;
        font-weight: 600;
        margin-top: 1rem;
    }

    .segment-box {
        background: rgba(96, 165, 250, 0.10);
        border: 1px solid rgba(96, 165, 250, 0.3);
        border-radius: 10px;
        padding: 0.6rem 1rem;
        color: rgba(255,255,255,0.70);
        font-size: 0.85rem;
        margin-top: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Hero ──────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero-card">
        <div class="hero-title">🎵 音訊 / 影片 → MP3 轉換器</div>
        <p class="hero-subtitle">上傳影片或音訊檔案，一鍵轉換為指定位元率的 MP3（支援超大影片自動分段合併）</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── 說明 ──────────────────────────────────────────────────────
_audio_fmt = "、".join(ext.upper() for ext in AUDIO_EXTENSIONS)
st.markdown(
    f'<div class="info-box">📌 支援格式：<b>MP4</b>（影片）、<b>{_audio_fmt}</b>（音訊）。<br>'
    f'上傳後選擇輸出位元率，點擊「開始轉換」即可下載 MP3。<br>'
    f'⚡ 超過 <b>{LARGE_FILE_THRESHOLD_MB} MB</b> 的影片檔將自動以每段 {SEGMENT_DURATION_SEC // 60} 分鐘分段轉換後合併。</div>',
    unsafe_allow_html=True,
)

# ── 上傳區 ────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "選擇影片或音訊檔案",
    type=ALL_EXTENSIONS,
    help="支援 MP4（影片）及 MP3、WAV、M4A、OGG、FLAC、AAC、WMA（音訊）",
)

# ── 設定區 ────────────────────────────────────────────────────
if uploaded_file is not None:
    file_size_mb = uploaded_file.size / (1024 * 1024)
    file_ext = Path(uploaded_file.name).suffix.lower().lstrip(".")
    is_audio_input = file_ext in AUDIO_EXTENSIONS
    is_large = (not is_audio_input) and (file_size_mb > LARGE_FILE_THRESHOLD_MB)

    st.markdown("---")

    # 大檔案提示
    if is_large:
        st.markdown(
            f'<div class="warn-box">⚠️ 檔案大小：<b>{file_size_mb:.1f} MB</b>，超過 {LARGE_FILE_THRESHOLD_MB} MB，'
            f'將自動分段（每段 {SEGMENT_DURATION_SEC // 60} 分鐘）轉換後合併為單一 MP3。</div>',
            unsafe_allow_html=True,
        )

    col1, col2 = st.columns(2)

    with col1:
        bitrate = st.selectbox(
            "輸出位元率（品質）",
            options=["64k", "96k", "128k", "192k", "256k", "320k"],
            index=1,
            help="位元率越低，檔案越小；位元率越高，音質越好",
        )

    with col2:
        output_name = st.text_input(
            "輸出檔案名稱（不含副檔名）",
            value=Path(uploaded_file.name).stem,
            help="預設使用原始檔名",
        )

    st.markdown("")

    # ── 轉換按鈕 ──────────────────────────────────────────────
    if st.button("🚀 開始轉換"):
        if not output_name.strip():
            st.error("❌ 請輸入輸出檔案名稱！")
        else:
            progress_bar = st.progress(0, text="準備中…")
            status_text  = st.empty()

            try:
                # ── 1. 改用手動管理暫存目錄，避免 Windows 的資料夾清理被鎖定而崩潰 ──
                tmp_dir = tempfile.mkdtemp()
                tmp_dir_path = Path(tmp_dir)

                # ── 儲存來源檔案 ──────────────────────────
                src_path = tmp_dir_path / uploaded_file.name
                status_text.markdown('<div class="segment-box">💾 寫入暫存檔案…</div>', unsafe_allow_html=True)
                with open(src_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                output_filename = f"{output_name.strip()}.mp3"
                out_dir = tmp_dir_path / "out"
                out_dir.mkdir(exist_ok=True)
                out_path = out_dir / output_filename

                # ═══════════════════════════════════════════
                # A) 音訊檔案：直接呼叫 ffmpeg 重新編碼
                # ═══════════════════════════════════════════
                if is_audio_input:
                    progress_bar.progress(15, text="讀取音訊檔案中…")
                    status_text.markdown(
                        f'<div class="segment-box">🔄 讀取 {file_ext.upper()} 檔案…</div>',
                        unsafe_allow_html=True,
                    )

                    progress_bar.progress(40, text="重新編碼為 MP3…")
                    status_text.markdown(
                        f'<div class="segment-box">🎧 以 {bitrate} 位元率輸出 MP3…</div>',
                        unsafe_allow_html=True,
                    )

                    # 直接呼叫 ffmpeg 進行轉檔
                    cmd = [
                        FFMPEG_EXE,
                        "-y",              # 覆寫輸出
                        "-i", str(src_path),
                        "-vn",             # 忽略影片軌
                        "-codec:a", "libmp3lame",
                        "-b:a", bitrate,
                        str(out_path),
                    ]
                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    if result.returncode != 0:
                        raise RuntimeError(
                            f"ffmpeg 轉檔失敗：{result.stderr.decode('utf-8', errors='replace')}"
                        )

                    progress_bar.progress(90, text="準備下載檔案…")

                # ═══════════════════════════════════════════
                # B) 影片檔案（MP4）：原有邏輯
                # ═══════════════════════════════════════════
                else:
                    progress_bar.progress(10, text="讀取影片中…")

                    # ── 取得影片總時長 ────────────────────────
                    with VideoFileClip(str(src_path)) as probe:
                        total_duration = probe.duration  # 秒
                        has_audio = probe.audio is not None

                    if not has_audio:
                        st.error("❌ 此影片檔案沒有音訊軌道，無法轉換！")
                        progress_bar.empty()
                        status_text.empty()
                        st.stop()

                    # ── 決定是否分段 ──────────────────────────
                    if not is_large:
                        # ── 小檔案：直接轉換 ──────────────────
                        progress_bar.progress(40, text="擷取音訊中…")
                        status_text.markdown('<div class="segment-box">🔄 直接轉換音訊…</div>', unsafe_allow_html=True)

                        with VideoFileClip(str(src_path)) as video:
                            progress_bar.progress(65, text="轉換音訊格式中…")
                            video.audio.write_audiofile(
                                str(out_path),
                                bitrate=bitrate,
                                logger=None,
                            )

                        progress_bar.progress(90, text="準備下載檔案…")

                    else:
                        # ── 大檔案：分段處理後合併 ────────────
                        num_segments = math.ceil(total_duration / SEGMENT_DURATION_SEC)
                        audio_clips = []

                        status_text.markdown(
                            f'<div class="segment-box">✂️ 共分為 <b>{num_segments}</b> 段，開始逐段擷取…</div>',
                            unsafe_allow_html=True,
                        )

                        # 打開主影片一次，從中切出多段音訊在記憶體中串接
                        main_video = VideoFileClip(str(src_path))

                        try:
                            for i in range(num_segments):
                                seg_start = i * SEGMENT_DURATION_SEC
                                seg_end   = min((i + 1) * SEGMENT_DURATION_SEC, total_duration)

                                pct = int(10 + (i / num_segments) * 50)
                                progress_bar.progress(
                                    pct,
                                    text=f"讀取第 {i+1}/{num_segments} 段音訊…",
                                )
                                status_text.markdown(
                                    f'<div class="segment-box">🎬 第 {i+1}/{num_segments} 段｜'
                                    f'{seg_start/60:.1f} 分 → {seg_end/60:.1f} 分</div>',
                                    unsafe_allow_html=True,
                                )

                                # 直接取得音訊片段，不寫出實體檔案
                                clip = main_video.subclipped(seg_start, seg_end)
                                audio_clips.append(clip.audio)

                            # ── 合併所有段落 ──────────────────────
                            progress_bar.progress(65, text="準備寫入合併後的完整音訊…")
                            status_text.markdown(
                                f'<div class="segment-box">🔗 正在編碼並寫入完整 MP3 (可能需要幾分鐘)…</div>',
                                unsafe_allow_html=True,
                            )

                            final_audio = concatenate_audioclips(audio_clips)
                            final_audio.write_audiofile(
                                str(out_path),
                                bitrate=bitrate,
                                logger=None,
                            )

                        finally:
                            # 確保手動關閉所有的資源
                            if 'final_audio' in locals():
                                final_audio.close()
                            for ac in audio_clips:
                                try:
                                    ac.close()
                                except:
                                    pass
                            main_video.close()
                            gc.collect()

                        progress_bar.progress(92, text="準備下載檔案…")

                # ── 讀取結果 ──────────────────────────────
                with open(out_path, "rb") as mp3_file:
                    mp3_bytes = mp3_file.read()

                progress_bar.progress(100, text="轉換完成！")
                status_text.empty()

                # ── 自動存入下載目錄 ───────────────────────
                downloads_dir = get_downloads_dir()
                downloads_dir.mkdir(parents=True, exist_ok=True)
                final_save_path = downloads_dir / output_filename
                shutil.copy2(out_path, final_save_path)

                # ── 顯示原始 vs 輸出大小 ─────────────────
                original_size_mb = file_size_mb
                output_size_mb   = len(mp3_bytes) / 1024 / 1024
                saved_pct = ((original_size_mb - output_size_mb) / original_size_mb * 100) if original_size_mb > 0 else 0

                extra = f"（共 {num_segments} 段合併）" if is_large else ""
                size_info = f"原始：{original_size_mb:.2f} MB → 輸出：{output_size_mb:.2f} MB"
                if saved_pct > 0:
                    size_info += f"（節省 {saved_pct:.1f}%）"

                st.markdown(
                    f'<div class="success-box">✅ 轉換成功{extra}！<br>{size_info}<hr style="margin: 0.5rem 0; border-color: rgba(52, 211, 153, 0.2);">'
                    f'📁 檔案已自動儲存至：<br><code>{final_save_path}</code></div>',
                    unsafe_allow_html=True,
                )

                st.download_button(
                    label=f"⬇️ [備用] 透過瀏覽器下載 {output_filename}",
                    data=mp3_bytes,
                    file_name=output_filename,
                    mime="audio/mpeg",
                    use_container_width=True,
                )

            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"❌ 轉換失敗：{e}")
                st.info("請確認已安裝所需套件：`pip install streamlit moviepy pydub`")
            finally:
                # ── 2. 在最後確保安全移除暫存擋，並忽略任何被占用的 Windows 鎖檔錯誤 ──
                if 'tmp_dir' in locals():
                    shutil.rmtree(tmp_dir, ignore_errors=True)

else:
    st.markdown(
        """
        <div style="text-align:center; color:rgba(255,255,255,0.35); margin-top:2rem; font-size:0.9rem;">
            ☝️ 請先上傳影片或音訊檔案
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── 頁尾 ──────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<p style="text-align:center; color:rgba(255,255,255,0.25); font-size:0.8rem;">Powered by Streamlit · MoviePy · pydub</p>',
    unsafe_allow_html=True,
)
