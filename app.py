import streamlit as st
from google import genai
from google.genai import types
import tempfile
import os
import time
import pathlib

# ================================
# 1. 介面與基本設定
# ================================
st.set_page_config(page_title="Casino Game AI 競品分析儀", page_icon="🎰", layout="wide")

import streamlit.components.v1 as components

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
st.markdown("快速比較自家產品與市面競品的遊玩體驗差異，並產生具有體感的結構化改善報告。")

# 側邊欄：設定
with st.sidebar:
    st.header("⚙️ 設定與權限")
    api_key_input = st.text_input("輸入 Gemini API Key", type="password")
    st.markdown("[🔑 點此前往 Google AI Studio 取得 API Key](https://aistudio.google.com/app/apikey)")

    st.markdown("---")
    st.markdown("### 💡 使用須知")
    st.error("⚠️ **非常重要 (需綁定付費資訊)**：\n分析影片會消耗大量 Token，無論使用哪種模型，**API Key 帳號都必須綁定付費資訊 (Pay as you go)** 才能成功執行，否則將會遇到 Quota 限制錯誤無法使用。")
    st.markdown("由於分析模型需要仔細核對影片長度與特效，按下分析後系統需要數分鐘時間進行影片讀取與處理。")
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
    st.subheader("🏠 自家遊戲")
    home_video = st.file_uploader("上傳自家遊戲影片 (支援 MP4/MOV)", type=["mp4", "mov", "avi"], key="home_vid")
    if home_video:
        st.video(home_video)

with col2:
    st.subheader("🔥 競品遊戲")
    comp_video = st.file_uploader("上傳競品遊戲影片 (支援 MP4/MOV)", type=["mp4", "mov", "avi"], key="comp_vid")
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

# ================================
# 3. 核心處理函式
# ================================
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

            myfile = client.files.upload(
                file=tmp_file_path,
                config=types.UploadFileConfig(mime_type=mime_type)
            )

            progress_bar = st.progress(0, text=f"⏳ 雲端處理中...準備開始處理 {file_label}")
            max_wait = 120   # 最多等 120 秒
            waited = 0

            # 持續輪詢，直到狀態不再是 PROCESSING
            while myfile.state.name == "PROCESSING" and waited < max_wait:
                # 模擬推進進度百分比 (從 5% 推進到 95%)
                percent = min(5 + int((waited / max_wait) * 90), 95)
                progress_bar.progress(percent, text=f"⏳ {file_label} 在雲端上傳中（已等待 {waited}s / {percent}%），這可能會花幾分鐘...")
                time.sleep(5)
                waited += 5
                myfile = client.files.get(name=myfile.name)

            progress_bar.empty()

            # 嚴格確認最終狀態必須為 ACTIVE
            if myfile.state.name != "ACTIVE":
                raise Exception(
                    f"{file_label} 處理失敗或逾時，最終狀態為：{myfile.state.name}（等待了 {waited}s）。"
                )

            st.success(f"✅ {file_label} 上傳完成！（狀態：{myfile.state.name}）")
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
第一支影片為【自家遊戲】，第二支影片為【競品遊戲】。{custom_focus_prompt}

分析重點需包含：
1. 核心節奏與操作感：Spin/發牌的速度、連押的流暢度、以及中獎前的『期待感營造（例如老虎機的聽牌/Scatter 特效延遲）』。
2. 視覺與聽覺回饋：小獎、大獎（Big Win / Mega Win）的慶祝特效（如金幣噴發、全螢幕動畫）、音效的疊加層次，以及長時間觀看是否容易視覺疲勞。
3. UI/UX 佈局：押注金額調整的直覺性、Spin 按鈕配置、餘額與贏分顯示的清晰度。
4. 特殊玩法展演：Free Spin（免費遊戲）或 Bonus Game 的轉場流暢度與規則清晰度。

請嚴格使用以下架構輸出 Markdown 報告（請善用粗體、列點與分隔線 `---` 讓一頁式的排版極度容易閱讀）：

---
## 1. 執行摘要
(請用一段話總結兩款產品在『玩家爽感營造』上的最大差異。)

---
## 2. 優劣勢對比
**自家優勢：**
- (優勢1)
- ... (共3點)

**自家需改善劣勢：**
- (劣勢1)
- ... (共3點)

---
## 3. 關鍵差異深度解析
(針對上述『分析重點』或『使用者特別指定的觀察重點』，給出具體的比較，必須明確指出影片中發生差異的『具體畫面』或『時間軸』作為佐證。)

---
## 4. 具體優化建議
(基於測試員觀點，提出 2~3 個自家產品可優先調整的開發/美術建議。)"""

        st.markdown("### 📊 競品體驗分析報告")
        
        # 前端 JS 實作的無縫讀取條
        progress_placeholder = st.empty()
        with progress_placeholder:
            components.html("""
            <!DOCTYPE html><html><body style="margin: 0; padding: 0; font-family: sans-serif; overflow: hidden;">
            <div style="width: 100%; height: 35px; background-color: #f0f2f6; border-radius: 6px; position: relative;">
                <div id="ai-progress-bar" style="width: 0%; height: 100%; background-color: #00CC96; border-radius: 6px; transition: width 1s linear;"></div>
                <div id="ai-progress-text" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: bold; color: #31333F;">👻 正在準備解析影片...</div>
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
        
        # 串流輸出到畫面，並取得完整的字串儲存
        full_response_text = st.write_stream(stream_parser())
        st.success("🎉 分析完成！")
        
        # 將 Markdown 轉成精美的 HTML
        import markdown
        html_content = markdown.markdown(full_response_text, extensions=['tables'])
        
        # 加上漂亮的中文字型與排版 CSS
        styled_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>競品體驗分析報告</title>
            <style>
                body {{
                    font-family: 'Helvetica Neue', Helvetica, Arial, 'Microsoft JhengHei', sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 900px;
                    margin: 0 auto;
                    padding: 2em;
                    background-color: #f9f9f9;
                }}
                h1, h2, h3 {{ color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 0.3em; }}
                ul, ol {{ padding-left: 20px; }}
                table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .container {{ background-color: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            </style>
        </head>
        <body>
            <div class="container">
                {html_content}
            </div>
        </body>
        </html>
        """
        
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
    
    # 如果不是剛剛分析完 (代表是按了其他按鈕觸發的重整)，就把存在記憶體的報告印出來
    if not st.session_state.get("just_analyzed", False):
        st.markdown("### 📊 競品體驗分析報告 (歷史紀錄)")
        st.markdown(st.session_state["report_md"])
    else:
        # 重設狀態，讓下次能正常顯示
        st.session_state["just_analyzed"] = False

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
