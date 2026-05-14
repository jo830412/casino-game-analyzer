import streamlit as st
from google import genai
from google.genai import types
import tempfile
import os
import time
import pathlib
import json
import re

# ================================
# 1. 介面與基本設定
# ================================
st.set_page_config(page_title="Casino Game AI 競品分析儀", page_icon="🎰", layout="wide")

import streamlit.components.v1 as components

# 注入 Google Fonts + 自定義 CSS
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap');
html, body, [class*="css"] {
    font-family: 'Noto Sans TC', 'Microsoft JhengHei', sans-serif !important;
}
h1 { letter-spacing: -0.02em; }
</style>
""", unsafe_allow_html=True)

# 初始化 Session State
if "is_analyzing" not in st.session_state:
    st.session_state["is_analyzing"] = False
if "analysis_done" not in st.session_state:
    st.session_state["analysis_done"] = False
if "report_md" not in st.session_state:
    st.session_state["report_md"] = ""
if "styled_html" not in st.session_state:
    st.session_state["styled_html"] = ""

st.title("🎰 Casino Game AI 競品分析儀")
st.caption("🏷️ 版本：v1.3.0 (全面體驗升級)")
st.markdown("快速比較自家產品與市面競品的遊玩體驗差異，並產生具有體感的結構化改善報告。")

# 側邊欄：設定
with st.sidebar:
    st.header("⚙️ 設定與權限")
    api_key_input = st.text_input("輸入 Gemini API Key", type="password")
    st.markdown("[🔑 點此前往 Google AI Studio 取得 API Key](https://aistudio.google.com/app/apikey)")

    st.markdown("---")
    with st.expander("📋 使用步驟（點我展開）", expanded=True):
        st.markdown("""
1. 🔑 輸入您的 Gemini API Key
2. 🎮 選擇遊戲類型
3. 📹 上傳自家與競品影片
4. ⏱️ (選填) 指定分析區間
5. 🎯 (選填) 填寫特別觀察重點
6. 🚀 點擊「開始深度分析」
7. 📊 查看報告與雷達圖
8. 💾 下載完整 HTML 報告（含圖表）
""")

    with st.expander("💡 計費與隱私須知", expanded=False):
        st.error("⚠️ **非常重要 (需綁定付費資訊)**：\n分析影片會消耗大量 Token，**API Key 帳號都必須綁定付費資訊 (Pay as you go)** 才能成功執行。")
        st.markdown("分析完畢後，雲端影片檔案將會被自動刪除，保護機密並確保不會浪費資源。")

    st.markdown("---")
    # 模型選擇
    model_choice = st.selectbox(
        "Gemini 模型",
        [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-3.1-pro-preview",
        ],
        help="Google 已停用 2.0 系列新用戶存取。請使用最新的 gemini-2.5-flash (快) 或 gemini-2.5-pro (精準)。"
    )



st.markdown("---")

# ================================
# 2. 檔案上傳與選項區
# ================================
col1, col2 = st.columns(2)
with col1:
    with st.container(border=True):
        st.subheader("🏠 自家遊戲")
        home_video = st.file_uploader("上傳自家遊戲影片 (MP4 / MOV / AVI)", type=["mp4", "mov", "avi"], key="home_vid")
        st.caption("📁 支援直接拖放 · 建議長度 30 秒～3 分鐘 · 請確認影片包含完整遊玩流程")
        if home_video:
            st.video(home_video)

with col2:
    with st.container(border=True):
        st.subheader("🔥 競品遊戲")
        comp_video = st.file_uploader("上傳競品遊戲影片 (MP4 / MOV / AVI)", type=["mp4", "mov", "avi"], key="comp_vid")
        st.caption("📁 支援直接拖放 · 建議長度 30 秒～3 分鐘 · 請確認影片包含完整遊玩流程")
        if comp_video:
            st.video(comp_video)

st.markdown("---")
game_type = st.selectbox(
    "這是哪種類型的博弈遊戲？",
    ["Slot 老虎機", "捕魚機", "撲克/棋牌", "其他"],
    help="輔助 AI 聚焦對應的核心特效節奏。"
)

custom_focus = st.text_area(
    "🎯 本次分析有什麼特別想關注的細節嗎？（選填）",
    help="例如：特別注意 Free Game 的過場速度、中大獎的音效層次、按鈕擺放位置等。"
)

st.markdown("---")
st.subheader("⏱️ 分析區間設定")
enable_time_range = st.checkbox("啟用指定分析區間 (僅分析精彩片段以節省 Token)", value=False)
time_range_prompt = ""
if enable_time_range:
    st.caption("請輸入「分:秒」格式（例如：00:30, 01:15）")
    # 使用 4 個欄位讓輸入框變小，且分成自家與競品
    col_h1, col_h2, col_c1, col_c2 = st.columns(4)
    home_start = col_h1.text_input("🏠 自家開始", value="00:00")
    home_end = col_h2.text_input("🏠 自家結束", value="00:30")
    comp_start = col_c1.text_input("🔥 競品開始", value="00:00")
    comp_end = col_c2.text_input("🔥 競品結束", value="00:30")
    
    time_range_prompt = (
        f"\n\n⏱️ **重要指令（時間區段分析）**：\n"
        f"- 對於【自家遊戲】，請嚴格僅針對影片中 **{home_start} 到 {home_end}** 的畫面進行分析。\n"
        f"- 對於【競品遊戲】，請嚴格僅針對影片中 **{comp_start} 到 {comp_end}** 的畫面進行分析。\n"
        f"請完全忽略上述時間區段以外的其他畫面。"
    )

# ================================
# 3. 核心處理函式
# ================================
def render_radar_chart(report_text):
    """
    嘗試從報告 Markdown 內找出 JSON 評分區塊，畫出雷達圖。
    回傳 (fig, clean_report, scores_dict | None)
    """
    import plotly.graph_objects as go
    categories = ['節奏爽快感', '視覺特效', '音效層次', 'UI直覺度', '期待感營造']
    match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', report_text)
    if not match:
        return None, report_text, None
    json_str = match.group(1)
    json_block_full = match.group(0)
    try:
        data = json.loads(json_str)
        def extract_scores(sd):
            if isinstance(sd, dict):
                return [float(sd.get(c, 0)) for c in categories]
            elif isinstance(sd, list) and len(sd) >= 5:
                return [float(v) for v in sd[:5]]
            return [0.0] * 5
        home_scores = extract_scores(data.get("home"))
        comp_scores = extract_scores(data.get("comp"))
        home_loop = home_scores + [home_scores[0]]
        comp_loop = comp_scores + [comp_scores[0]]
        cat_loop  = categories  + [categories[0]]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=home_loop, theta=cat_loop, fill='toself', name='自家遊戲',
            line_color='#3b82f6', fillcolor='rgba(59,130,246,0.3)',
            mode='lines+markers+text',
            text=[f"{v:.0f}" for v in home_scores] + [""],
            textposition='top center'
        ))
        fig.add_trace(go.Scatterpolar(
            r=comp_loop, theta=cat_loop, fill='toself', name='競品遊戲',
            line_color='#ef4444', fillcolor='rgba(239,68,68,0.3)',
            mode='lines+markers+text',
            text=[f"{v:.0f}" for v in comp_scores] + [""],
            textposition='top center'
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
            showlegend=True, title="🎯 競品體驗維度對比"
        )
        sections = re.split(r'(?m)^---\s*$', report_text)
        clean_sections = [s for s in sections if json_block_full not in s]
        clean = "\n\n---\n\n".join(clean_sections).strip()
        return fig, clean, {"home": home_scores, "comp": comp_scores}
    except Exception:
        return None, report_text, None

def upload_video_to_gemini(client: genai.Client, uploaded_file, file_label: str = "") -> types.File:
    """
    將 Streamlit 的上傳檔案暫存到硬碟後使用新版 File API 上傳至 Gemini，
    並設計阻擋等待機制直到影片由 PROCESSING 變成 ACTIVE 狀態。
    """
    with st.spinner(f"正在傳送 {file_label} 至 Google AI..."):
        ext = pathlib.Path(uploaded_file.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            tmp_file.write(uploaded_file.read())
            tmp_file_path = tmp_file.name

        try:
            mime_map = {".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo"}
            mime_type = mime_map.get(ext.lower(), "video/mp4")

            upload_bar = st.progress(0, text=f"📤 {file_label} 正在上傳至 Google AI 雲端...") 
            myfile = client.files.upload(
                file=tmp_file_path,
                config=types.UploadFileConfig(mime_type=mime_type)
            )
            upload_bar.progress(30, text=f"✅ {file_label} 上傳完成，等待雲端處理...")

            max_wait = 120   # 最多等 120 秒
            waited = 0

            # 持續輪詢，直到狀態不再是 PROCESSING
            while myfile.state.name == "PROCESSING" and waited < max_wait:
                percent = min(30 + int((waited / max_wait) * 65), 95)
                upload_bar.progress(percent, text=f"⚙️ {file_label} 雲端處理中（{waited}s），請稍候...")
                time.sleep(5)
                waited += 5
                myfile = client.files.get(name=myfile.name)

            upload_bar.progress(100, text=f"🎉 {file_label} 就緒！")
            time.sleep(0.4)
            upload_bar.empty()

            # 嚴格確認最終狀態必須為 ACTIVE
            if myfile.state.name != "ACTIVE":
                raise Exception(
                    f"{file_label} 處理失敗或逾時，最終狀態為：{myfile.state.name}（等待了 {waited}s）。"
                )

            st.toast(f"✅ {file_label} 上傳完成！", icon="🎉")
            return myfile

        finally:
            if os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)



# ================================
# 4. 執行按鈕與報告渲染區
# ================================
def trigger_analysis():
    st.session_state["is_analyzing"] = True
    st.session_state["analysis_done"] = False

st.button("🚀 開始深度分析", on_click=trigger_analysis, disabled=st.session_state.get("is_analyzing", False), use_container_width=True, type="primary")

if st.session_state.get("is_analyzing", False):
    if not api_key_input:
        st.error("請先於左側欄位輸入 Gemini API Key。")
        st.session_state["is_analyzing"] = False
        st.stop()

    if not home_video or not comp_video:
        st.error("請確保「自家遊戲」與「競品遊戲」皆已成功上傳影片。")
        st.session_state["is_analyzing"] = False
        st.stop()

    # 建立新版 Client
    client = genai.Client(api_key=api_key_input)
    file1, file2 = None, None

    try:
        # 上傳兩段影片
        file1 = upload_video_to_gemini(client, home_video, "自家遊戲影片")
        file2 = upload_video_to_gemini(client, comp_video, "競品遊戲影片")

        # 定義 Prompt 變數
        custom_focus_prompt = f"\n\n🚨 **使用者特別指定的觀察重點**：\n{custom_focus}\n請特別針對上述要求進行分析與解答。" if custom_focus.strip() else ""
        
        prompt = f"""你是一位資深博弈遊戲測試員與 UX 研究員。請仔細觀看兩支【{game_type}】的實機遊玩影片，進行深度的競品差異分析，並產生結構化報告。
第一支影片為【自家遊戲】，第二支影片為【競品遊戲】。{custom_focus_prompt}{time_range_prompt}

分析重點需包含：
1. 核心節奏與操作感：Spin/發牌的速度、連押的流暢度、以及中獎前的『期待感營造（例如老虎機的聽牌/Scatter 特效延遲）』。
2. 視覺與聽覺回饋：小獎、大獎（Big Win / Mega Win）的慶祝特效（如金幣噴發、全螢幕動畫）、音效的疊加層次，以及長時間觀看是否容易視覺疲勞。
3. UI/UX 佈局：押注金額調整的直覺性、Spin 按鈕配置、餘額與贏分顯示的清晰度。
4. 特殊玩法展演：Free Spin（免費遊戲）或 Bonus Game 的轉場流暢度與規則清晰度。

請嚴格使用以下 Markdown 架構輸出報告（請善用粗體、列點與分隔線 `---` 讓排版極度容易閱讀，並加入適當的 Emoji 增添質感）：

## 🎯 1. 執行摘要
> (請用一段話精準總結兩款產品在『玩家爽感營造』上的最大差異。)

---
## ⚖️ 2. 優劣勢對比

### 🌟 自家產品優勢：
- (具體優勢 1)
- ... (共 3 點)

### ⚠️ 自家需改善劣勢：
- (具體劣勢 1)
- ... (共 3 點)

---
## 🔍 3. 關鍵差異深度解析
(針對上述『分析重點』或『使用者特別指定的觀察重點』，給出具體的比較，必須明確指出影片中發生差異的『具體畫面』或『時間軸』作為佐證。)

---
## 💡 4. 具體優化建議
(基於測試員觀點，提出 2~3 個自家產品可優先調整的開發/美術建議。請具體說明「如何改」以及「預期的改善效果」。)

---
## 📊 5. 數據化評分
請為兩款產品在以下 5 個維度給出 1~10 分的客觀評分，並**嚴格將結果以 JSON 格式包裝在 ```json 與 ``` 區塊內**，放置於報告的最尾端。
維度包含：節奏爽快感、視覺特效、音效層次、UI直覺度、期待感營造。
格式範例：
```json
{{
  "home": {{"節奏爽快感": 8, "視覺特效": 7, "音效層次": 6, "UI直覺度": 8, "期待感營造": 7}},
  "comp": {{"節奏爽快感": 9, "視覺特效": 9, "音效層次": 8, "UI直覺度": 7, "期待感營造": 9}}
}}
```
"""

        st.markdown("### 📊 競品體驗分析報告")
        
        # 前端 JS 實作的無縫讀取條
        progress_placeholder = st.empty()
        with progress_placeholder:
            components.html("""
            <!DOCTYPE html><html><body style="margin: 0; padding: 0; font-family: sans-serif; overflow: hidden; background-color: transparent;">
            <div style="width: 100%; height: 35px; background-color: #262730; border-radius: 6px; position: relative; border: 1px solid #444;">
                <div id="ai-progress-bar" style="width: 0%; height: 100%; background-color: #FFC107; border-radius: 6px; transition: width 1s linear;"></div>
                <div id="ai-progress-text" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: bold; color: #FAFAFA; text-shadow: 1px 1px 2px rgba(0,0,0,0.8);">👻 正在準備解析影片...</div>
            </div>
            <script>
                let pb = document.getElementById('ai-progress-bar');
                let pt = document.getElementById('ai-progress-text');
                let t = 0; let total = 45; // 預期等待 45 秒
                let iv = setInterval(() => {
                    t++;
                    let pct = Math.min((t/total)*95, 95);
                    if(pb) pb.style.width = pct + '%';
                    if(pt) {
                        if (t < 10) pt.innerText = '👀 正在以 10 倍速解析影片中... (' + Math.floor(pct) + '%)';
                        else if (t < 25) pt.innerText = '🧠 正在對比兩款遊戲的節奏與特效差異... (' + Math.floor(pct) + '%)';
                        else if (t < 40) pt.innerText = '📝 正在整理結構化總結與最佳化建議... (' + Math.floor(pct) + '%)';
                        else pt.innerText = '✨ 報告即將出爐，請稍候... (' + Math.floor(pct) + '%)';
                    }
                    if (t >= total) clearInterval(iv);
                }, 1000);
            </script>
            </body></html>
            """, height=40)

        response_stream = client.models.generate_content_stream(
            model=model_choice,
            contents=[
                types.Part.from_uri(file_uri=file1.uri, mime_type=file1.mime_type),
                types.Part.from_uri(file_uri=file2.uri, mime_type=file2.mime_type),
                prompt,
            ]
        )
        
        def stream_parser():
            first = True
            for chunk in response_stream:
                if first:
                    progress_placeholder.empty() # 清除原本的動態 HTML 進度條
                    first = False
                if chunk.text:
                    yield chunk.text
        
        full_response_text = st.write_stream(stream_parser())
        st.toast("🎉 分析完成！", icon="🎉")
        
        # 將 Markdown 轉成精美的 HTML（含雷達圖）
        import markdown as md_lib
        # 先解析雷達圖，以便把圖表嵌入 HTML
        _fig_export, _clean_export, _scores_export = render_radar_chart(full_response_text)
        radar_html_embed = _fig_export.to_html(full_html=False, include_plotlyjs='inline') if _fig_export else ""
        html_body = md_lib.markdown(_clean_export if _clean_export else full_response_text, extensions=['tables'])

        styled_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>競品體驗分析報告</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Noto Sans TC','Microsoft JhengHei',sans-serif; line-height:1.8; color:#2d3748; background:#edf2f7; margin:0; padding:40px 20px; }}
        .container {{ max-width:850px; margin:0 auto; background:#fff; padding:40px 50px; border-radius:12px; box-shadow:0 10px 25px rgba(0,0,0,.05); }}
        h2 {{ border-bottom:3px solid #ebf8ff; padding-bottom:.4em; color:#2b6cb0; margin-top:1.5em; }}
        blockquote {{ margin:1.5em 0; padding:1em 1.5em; background:#ebf8ff; border-left:5px solid #3182ce; border-radius:0 8px 8px 0; color:#2c5282; font-weight:500; }}
        ul,ol {{ padding-left:24px; margin-bottom:1.5em; }} li {{ margin-bottom:.5em; }}
        table {{ border-collapse:collapse; width:100%; margin:2em 0; border-radius:8px; overflow:hidden; box-shadow:0 4px 6px rgba(0,0,0,.05); }}
        th,td {{ padding:12px 15px; text-align:left; }} th {{ background:#4299e1; color:#fff; font-weight:600; }}
        tr:nth-child(even) {{ background:#f7fafc; }}
        hr {{ border:0; height:1px; background:#e2e8f0; margin:3em 0; }}
    </style>
</head>
<body>
    <div class="container">
        {radar_html_embed}
        {html_body}
    </div>
</body>
</html>"""

        # 存入 session_state 避免畫面重整消失
        st.session_state["report_md"] = full_response_text
        st.session_state["styled_html"] = styled_html
        st.session_state["analysis_done"] = True
        st.session_state["just_analyzed"] = True

    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "Quota exceeded" in error_msg:
            st.error("🚨 **API 額度已耗盡 (Quota Exceeded)**")
            st.warning("⚠️ **原因**：您目前使用的 API Key 處於「免費 Tier (Free Tier)」，而免費方案上傳分析兩部影片極易超過長內容的 Token 限制，或是您的地區剛好未開放免費額度。")
            st.info("👉 **解決方法**：前往 [Google AI Studio 方案頁面](https://aistudio.google.com/plan) 設定您的帳單資訊（Pay as you go）。不用擔心，影片測試的花費通常非常低巧，綁定後重新點擊分析即可順利完成。")
            with st.expander("詳細原始錯誤訊息"):
                st.write(error_msg)
        else:
            st.error(f"分析過程中發生異常：{e}")

    finally:
        # 清除雲端伺服器上的暫存影片，節省 Quota
        for f in [file1, file2]:
            if f:
                try:
                    client.files.delete(name=f.name)
                except Exception:
                    pass

        # 不論成功失敗，都要解除按鈕鎖定並重整畫面
        st.session_state["is_analyzing"] = False
        st.rerun()

# ================================
# 5. 結果渲染與狀態保留區
# ================================

if st.session_state.get("analysis_done", False):
    st.markdown("---")
    st.markdown("### 📊 競品體驗分析報告")
    
    tab1, tab2 = st.tabs(["📄 AI 結構化報告", "💾 下載與匯出"])
    
    with tab1:
        # 解析雷達圖與移除原始 JSON
        fig, clean_report, scores = render_radar_chart(st.session_state["report_md"])

        # 評分 Metric 卡片
        if scores:
            home_avg = sum(scores["home"]) / len(scores["home"])
            comp_avg = sum(scores["comp"]) / len(scores["comp"])
            gap = comp_avg - home_avg
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("🏠 自家平均分", f"{home_avg:.1f} / 10")
            mc2.metric("🔥 競品平均分", f"{comp_avg:.1f} / 10")
            mc3.metric("🎯 差距", f"{abs(gap):.1f} 分",
                       delta=f"自家落後 {abs(gap):.1f} 分" if gap > 0 else f"自家領先 {abs(gap):.1f} 分",
                       delta_color="inverse" if gap > 0 else "normal")
            st.markdown("---")

        if fig:
            st.plotly_chart(fig, use_container_width=True)

        # 由於使用 st.rerun() 會重繪畫面，串流產生的文字會消失，所以在此直接顯示歷史報告
        with st.container(border=True):
            st.markdown(clean_report)

    with tab2:
        st.markdown("您可以將報告下載為精美的 HTML 格式以供保存，或下載 Markdown 備份。")
        # 顯示下載按鈕
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 下載 HTML 報告 (推薦，保留排版)",
                data=st.session_state["styled_html"],
                file_name="競品分析報告.html",
                mime="text/html",
                type="primary",
                use_container_width=True
            )
        with col2:
            st.download_button(
                label="📝 下載 Markdown 報告 (原始備份)",
                data=st.session_state["report_md"],
                file_name="競品分析報告.md",
                mime="text/markdown",
                use_container_width=True
            )

    st.caption("💡 小提示：上方的下載按鈕就算點擊後，這份報告也**不會再消失**了！")
