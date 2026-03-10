import streamlit as st
import os
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path
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

# ── 支援的音訊格式 ─────────────────────────────────────────────
AUDIO_EXTENSIONS = ["mp3", "wav", "m4a", "ogg", "flac", "aac", "wma"]

# ── 頁面設定 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="多音訊合併器",
    page_icon="🎶",
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
        background: linear-gradient(90deg, #f472b6, #a78bfa, #60a5fa);
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

    .file-list-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }

    .file-list-title {
        color: rgba(255,255,255,0.85);
        font-weight: 600;
        font-size: 0.95rem;
        margin-bottom: 0.6rem;
    }

    .file-item {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.4rem 0.6rem;
        margin-bottom: 0.3rem;
        background: rgba(255,255,255,0.04);
        border-radius: 8px;
        color: rgba(255,255,255,0.70);
        font-size: 0.88rem;
    }

    .file-item-num {
        background: linear-gradient(135deg, #7c3aed, #2563eb);
        color: white;
        border-radius: 50%;
        width: 22px;
        height: 22px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.72rem;
        font-weight: 700;
        flex-shrink: 0;
    }

    .file-item-name {
        flex-grow: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .file-item-size {
        color: rgba(255,255,255,0.40);
        font-size: 0.78rem;
        flex-shrink: 0;
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

    .order-instructions {
        background: rgba(251, 191, 36, 0.08);
        border-left: 4px solid #fbbf24;
        border-radius: 8px;
        padding: 0.6rem 1rem;
        color: rgba(255,255,255,0.65);
        font-size: 0.85rem;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Hero ──────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero-card">
        <div class="hero-title">🎶 多音訊合併器</div>
        <p class="hero-subtitle">上傳多個音訊檔案，一鍵合併為單一 MP3</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── 說明 ──────────────────────────────────────────────────────
_audio_fmt = "、".join(ext.upper() for ext in AUDIO_EXTENSIONS)
st.markdown(
    f'<div class="info-box">📌 支援格式：<b>{_audio_fmt}</b><br>'
    f'可同時上傳多個音訊檔案，調整順序後點擊「開始合併」即可下載合併後的 MP3。</div>',
    unsafe_allow_html=True,
)

# ── 上傳區 ────────────────────────────────────────────────────
uploaded_files = st.file_uploader(
    "選擇音訊檔案（可多選）",
    type=AUDIO_EXTENSIONS,
    accept_multiple_files=True,
    help=f"支援 {_audio_fmt}，可一次選取多個檔案",
)

# ── 主邏輯 ────────────────────────────────────────────────────
if uploaded_files and len(uploaded_files) > 0:
    st.markdown("---")

    # ── 顯示已上傳的檔案清單 ──────────────────────────────────
    # 使用 session_state 管理檔案排序
    if "file_order" not in st.session_state:
        st.session_state.file_order = list(range(len(uploaded_files)))

    # 若上傳檔案數量改變，重設排序
    if len(st.session_state.file_order) != len(uploaded_files):
        st.session_state.file_order = list(range(len(uploaded_files)))

    # 建立排序後的檔案列表
    ordered_files = [uploaded_files[i] for i in st.session_state.file_order]

    # ── 排序提示 ──────────────────────────────────────────────
    st.markdown(
        '<div class="order-instructions">💡 合併順序即為下方檔案列表順序。'
        "使用每個檔案旁邊的數字欄位來調整順序。</div>",
        unsafe_allow_html=True,
    )

    # ── 檔案列表與排序 ────────────────────────────────────────
    st.markdown('<div class="file-list-card">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="file-list-title">📋 已上傳 {len(uploaded_files)} 個檔案</div>',
        unsafe_allow_html=True,
    )

    new_order = {}
    for idx, uf in enumerate(ordered_files):
        file_size = uf.size / (1024 * 1024)
        ext = Path(uf.name).suffix.lower().lstrip(".")

        col_num, col_name = st.columns([1, 5])
        with col_num:
            pos = st.number_input(
                f"順序_{idx}",
                min_value=1,
                max_value=len(uploaded_files),
                value=idx + 1,
                step=1,
                key=f"order_{idx}",
                label_visibility="collapsed",
            )
            new_order[idx] = pos
        with col_name:
            st.markdown(
                f'<div class="file-item">'
                f'<span class="file-item-num">{idx + 1}</span>'
                f'<span class="file-item-name">🎵 {uf.name}</span>'
                f'<span class="file-item-size">{file_size:.1f} MB · {ext.upper()}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("</div>", unsafe_allow_html=True)

    # ── 根據使用者設定的順序重排 ──────────────────────────────
    if st.button("🔄 套用排序"):
        # 用 position 排序来重新排列 file_order
        sorted_pairs = sorted(new_order.items(), key=lambda x: x[1])
        new_indices = [st.session_state.file_order[pair[0]] for pair in sorted_pairs]
        st.session_state.file_order = new_indices
        st.rerun()

    st.markdown("")

    # ── 設定區 ────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        bitrate = st.selectbox(
            "輸出位元率（品質）",
            options=["64k", "96k", "128k", "192k", "256k", "320k"],
            index=3,
            help="位元率越低，檔案越小；位元率越高，音質越好",
        )

    with col2:
        output_name = st.text_input(
            "輸出檔案名稱（不含副檔名）",
            value="merged_audio",
            help="合併後的 MP3 檔案名稱",
        )

    st.markdown("")

    # ── 合併按鈕 ──────────────────────────────────────────────
    if st.button("🚀 開始合併"):
        if not output_name.strip():
            st.error("❌ 請輸入輸出檔案名稱！")
        elif len(uploaded_files) < 2:
            st.error("❌ 請至少上傳 2 個音訊檔案才能進行合併！")
        else:
            progress_bar = st.progress(0, text="準備中…")
            status_text = st.empty()

            try:
                # ── 1. 建立暫存目錄 ──────────────────────────
                tmp_dir = tempfile.mkdtemp()
                tmp_dir_path = Path(tmp_dir)

                out_dir = tmp_dir_path / "out"
                out_dir.mkdir(exist_ok=True)

                # ── 2. 逐一寫入上傳的檔案到暫存 ─────────────
                progress_bar.progress(5, text="寫入暫存檔案中…")
                status_text.markdown(
                    '<div class="segment-box">💾 儲存上傳的音訊檔案…</div>',
                    unsafe_allow_html=True,
                )

                src_paths = []
                for i, uf in enumerate(ordered_files):
                    # 使用安全的檔名（避免特殊字元問題）
                    safe_name = f"input_{i:03d}{Path(uf.name).suffix}"
                    src_path = tmp_dir_path / safe_name
                    with open(src_path, "wb") as f:
                        f.write(uf.getbuffer())
                    src_paths.append(src_path)

                num_files = len(src_paths)

                # ── 3. 逐一轉換為統一的 WAV 中間格式 ─────────
                wav_paths = []
                for i, src in enumerate(src_paths):
                    pct = int(10 + (i / num_files) * 40)
                    progress_bar.progress(
                        pct,
                        text=f"轉換第 {i + 1}/{num_files} 個檔案…",
                    )
                    status_text.markdown(
                        f'<div class="segment-box">🔄 轉換 {ordered_files[i].name} → WAV…</div>',
                        unsafe_allow_html=True,
                    )

                    wav_path = tmp_dir_path / f"temp_{i:03d}.wav"
                    cmd = [
                        FFMPEG_EXE,
                        "-y",
                        "-i", str(src),
                        "-vn",
                        "-acodec", "pcm_s16le",
                        "-ar", "44100",
                        "-ac", "2",
                        str(wav_path),
                    ]
                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    if result.returncode != 0:
                        raise RuntimeError(
                            f"轉換 {ordered_files[i].name} 失敗：{result.stderr.decode('utf-8', errors='replace')}"
                        )
                    wav_paths.append(wav_path)

                # ── 4. 使用 ffmpeg concat 合併所有 WAV ───────
                progress_bar.progress(55, text="合併音訊中…")
                status_text.markdown(
                    f'<div class="segment-box">🔗 正在合併 {num_files} 個音訊檔案…</div>',
                    unsafe_allow_html=True,
                )

                # 建立 concat 清單檔
                concat_list_path = tmp_dir_path / "concat_list.txt"
                with open(concat_list_path, "w", encoding="utf-8") as f:
                    for wp in wav_paths:
                        # ffmpeg concat 格式要求使用正斜線並轉義特殊字元
                        safe_path = str(wp).replace("\\", "/").replace("'", "'\\''")
                        f.write(f"file '{safe_path}'\n")

                # 合併為 WAV
                merged_wav = tmp_dir_path / "merged.wav"
                cmd = [
                    FFMPEG_EXE,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_list_path),
                    "-c", "copy",
                    str(merged_wav),
                ]
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"合併失敗：{result.stderr.decode('utf-8', errors='replace')}"
                    )

                # ── 5. 將合併的 WAV 轉為 MP3 ────────────────
                progress_bar.progress(75, text="編碼為 MP3…")
                status_text.markdown(
                    f'<div class="segment-box">🎧 以 {bitrate} 位元率編碼輸出 MP3…</div>',
                    unsafe_allow_html=True,
                )

                output_filename = f"{output_name.strip()}.mp3"
                out_path = out_dir / output_filename
                cmd = [
                    FFMPEG_EXE,
                    "-y",
                    "-i", str(merged_wav),
                    "-vn",
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
                        f"MP3 編碼失敗：{result.stderr.decode('utf-8', errors='replace')}"
                    )

                # ── 6. 讀取結果 ──────────────────────────────
                progress_bar.progress(90, text="準備下載檔案…")
                with open(out_path, "rb") as mp3_file:
                    mp3_bytes = mp3_file.read()

                progress_bar.progress(100, text="合併完成！")
                status_text.empty()

                # ── 自動存入下載目錄 ───────────────────────
                downloads_dir = get_downloads_dir()
                downloads_dir.mkdir(parents=True, exist_ok=True)
                final_save_path = downloads_dir / output_filename
                shutil.copy2(out_path, final_save_path)

                # ── 顯示結果資訊 ─────────────────────────────
                total_input_mb = sum(uf.size for uf in uploaded_files) / (1024 * 1024)
                output_size_mb = len(mp3_bytes) / 1024 / 1024

                st.markdown(
                    f'<div class="success-box">✅ 合併成功！已將 {num_files} 個音訊檔案合併為一個 MP3<br>'
                    f"原始總計：{total_input_mb:.2f} MB → 輸出：{output_size_mb:.2f} MB<hr style=\"margin: 0.5rem 0; border-color: rgba(52, 211, 153, 0.2);\">"
                    f"📁 檔案已自動儲存至：<br><code>{final_save_path}</code></div>",
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
                st.error(f"❌ 合併失敗：{e}")
                st.info("請確認已安裝所需套件：`pip install streamlit imageio-ffmpeg`")
            finally:
                # ── 安全清除暫存檔案 ──────────────────────────
                if "tmp_dir" in locals():
                    shutil.rmtree(tmp_dir, ignore_errors=True)

else:
    st.markdown(
        """
        <div style="text-align:center; color:rgba(255,255,255,0.35); margin-top:2rem; font-size:0.9rem;">
            ☝️ 請先上傳音訊檔案（可多選）
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── 頁尾 ──────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<p style="text-align:center; color:rgba(255,255,255,0.25); font-size:0.8rem;">Powered by Streamlit · FFmpeg</p>',
    unsafe_allow_html=True,
)
