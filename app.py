import streamlit as st
from google import genai
from google.genai import types
import tempfile
import os
import time
import pathlib

st.set_page_config(page_title="Casino Game AI Analyzer", layout="wide")

import streamlit.components.v1 as components

if "is_analyzing" not in st.session_state:
      st.session_state["is_analyzing"] = False
  if "analysis_done" not in st.session_state:
        st.session_state["analysis_done"] = False
    if "report_md" not in st.session_state:
          st.session_state["report_md"] = ""
      if "styled_html" not in st.session_state:
            st.session_state["styled_html"] = ""

st.title("Casino Game AI Analyzer")
st.markdown("Compare game experiences and generate reports.")

with st.sidebar:
      st.header("Settings")
      api_key_input = st.text_input("Gemini API Key", type="password")

    model_choice = st.selectbox(
              "Gemini Model",
              ["gemini-2.0-flash", "gemini-2.0-pro-exp-02-05"]
    )

col1, col2 = st.columns(2)
with col1:
      st.subheader("Home Game")
      home_video = st.file_uploader("Upload home video", type=["mp4", "mov"], key="home_vid")
  with col2:
        st.subheader("Competitor Game")
        comp_video = st.file_uploader("Upload competitor video", type=["mp4", "mov"], key="comp_vid")

def upload_video_to_gemini(client, uploaded_file, label):
      with st.spinner(f"Uploading {label}..."):
                ext = pathlib.Path(uploaded_file.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                              tmp.write(uploaded_file.read())
                              path = tmp.name
                          try:
                                        f = client.files.upload(file=path)
                                        while f.state.name == "PROCESSING":
                                                          time.sleep(2)
                                                          f = client.files.get(name=f.name)
                                                      return f
finally:
            if os.path.exists(path): os.remove(path)

  if st.button("Start Analysis", disabled=st.session_state["is_analyzing"]):
        if not api_key_input or not home_video or not comp_video:
                  st.error("Missing info")
  else:
        st.session_state["is_analyzing"] = True
            client = genai.Client(api_key=api_key_input)
        try:
                      f1 = upload_video_to_gemini(client, home_video, "Home")
                      f2 = upload_video_to_gemini(client, comp_video, "Comp")
                      resp = client.models.generate_content(
                          model=model_choice,
                          contents=[f1, f2, "Analyze these two videos."]
                      )
                      st.write(resp.text)
                      st.session_state["report_md"] = resp.text
                      st.session_state["analysis_done"] = True
except Exception as e:
            st.error(str(e))
finally:
            st.session_state["is_analyzing"] = False
  
