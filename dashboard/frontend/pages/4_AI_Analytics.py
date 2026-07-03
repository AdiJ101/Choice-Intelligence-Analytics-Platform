"""
dashboard/frontend/pages/4_AI_Analytics.py — AI Analytics.
Map-reduce Customer + Company intelligence. (Chatbot is the global floating widget.)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from datetime import date, timedelta
import pandas as pd
import streamlit as st

from dashboard.frontend.api_client import client
from dashboard.frontend.styles import (
    inject_css, navbar, floating_chat, section_header, insight_card,
    ACCENT, ACCENT_LIGHT, TEXT_PRIMARY, TEXT_MUTED, TEXT_SECONDARY,
    CARD_BG, BORDER, SHADOW, RADIUS, RADIUS_SM,
)

st.set_page_config(page_title="AI Analytics", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")
inject_css()
navbar("AI_Analytics")

st.markdown(f"""
<div style="padding:8px 0 8px 0">
    <h1 style="font-size:36px;font-weight:700;margin:0">AI Analytics</h1>
    <p style="font-size:15px;color:{TEXT_MUTED};margin:4px 0 0 0">
        AI-powered intelligence from YouTube comments, video titles, and descriptions
    </p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
try:
    categories = client.get_categories()
except Exception:
    categories = []

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 2])
sel_cat   = col1.selectbox("Brand", ["All Brands"] + [c["category_name"] for c in categories], label_visibility="collapsed")
date_from = col2.date_input("From", value=date.today() - timedelta(days=90))
date_to   = col3.date_input("To",   value=date.today())
cat_param = sel_cat if sel_cat != "All Brands" else None

_JOB_ID_KEY = "ai_job_id"

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
run_analysis = col4.button("Generate Analysis", type="primary", use_container_width=True)
clear_analysis = col5.button("Clear Analysis", type="secondary", use_container_width=True)

# Helper to convert to local time
def to_local_time(val, format_str="%b %d, %H:%M:%S", default="N/A"):
    if not val:
        return default
    try:
        dt = pd.to_datetime(val)
        if dt.tzinfo is not None:
            dt = dt.to_pydatetime().astimezone(None)
        return dt.strftime(format_str)
    except:
        return str(val)

# 1. Fetch persistent last analysis cache
try:
    last_analysis = client.get_last_ai_analytics()
except Exception:
    last_analysis = {}

# 2. Check active job status on backend (serves as absolute source of truth!)
active_job = False
job_error = None
active_job_id = st.session_state.get(_JOB_ID_KEY)

try:
    active_job_status = client.get_active_ai_job()
    status = active_job_status.get("status")
    
    if status == "generating":
        active_job = True
        st.session_state[_JOB_ID_KEY] = active_job_status.get("job_id")
    elif status == "failed":
        job_error = active_job_status.get("error", "Unknown error occurred.")
        if _JOB_ID_KEY in st.session_state:
            del st.session_state[_JOB_ID_KEY]
    elif status == "completed":
        if _JOB_ID_KEY in st.session_state:
            del st.session_state[_JOB_ID_KEY]
        # Reload persistent cache immediately
        try:
            last_analysis = client.get_last_ai_analytics()
        except:
            pass
        st.rerun()
except Exception as e:
    # If connection fails temporarily, keep using session state if it exists
    if active_job_id:
        active_job = True

# 3. Start a new job
if run_analysis:
    try:
        resp = client.start_ai_analytics_job(
            category=cat_param,
            date_from=date_from,
            date_to=date_to,
        )
        st.session_state[_JOB_ID_KEY] = resp["job_id"]
        st.rerun()
    except Exception as e:
        st.error(f"Failed to start analysis: {e}")
        st.stop()

# 4. Clear analysis cache
if clear_analysis:
    try:
        client.clear_last_ai_analytics()
        if _JOB_ID_KEY in st.session_state:
            del st.session_state[_JOB_ID_KEY]
        st.rerun()
    except Exception as e:
        st.error(f"Failed to clear analysis: {e}")
        st.stop()

# 5. Render Active Job Banner
if active_job:
    st.info("⏳ A new analysis is currently generating in the background. The previous analysis is displayed below.")

# 6. Render Job Failures
if job_error:
    st.warning(f"Analysis failed: {job_error}", icon="⚠️")

# 7. Render Analysis Content or Landing Page
if last_analysis and "result" in last_analysis:
    result = last_analysis["result"]
    metadata = last_analysis.get("metadata", {})
    
    if result.get("error"):
        st.warning(result["error"], icon="⚠️")
    else:
        # Display the Brand and Timeline details prominently
        st.markdown(f"""
        <div style="
            background:{CARD_BG};
            border:1px solid {BORDER};
            border-radius:{RADIUS_SM};
            padding:16px 20px;
            margin-bottom:24px;
            box-shadow:{SHADOW};
        ">
            <span style="font-size:12px;font-weight:600;color:{ACCENT};text-transform:uppercase;letter-spacing:0.05em">Active Analysis Details</span>
            <div style="display:flex;flex-wrap:wrap;gap:24px;margin-top:8px;font-size:14px;color:{TEXT_SECONDARY}">
                <div>🏷️ Brand: <strong>{metadata.get('category', 'All Brands')}</strong></div>
                <div>📅 Timeline: <strong>{to_local_time(metadata.get('date_from'), "%b %d, %Y", default="All Time")} to {to_local_time(metadata.get('date_to'), "%b %d, %Y", default="Now")}</strong></div>
                <div>⏱️ Generated At: <strong>{to_local_time(result.get('generated_at'), "%b %d, %Y, %H:%M:%S", default="N/A")}</strong></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        section_header("Customer Intelligence", "What customers are talking about — from comments and engagement signals")
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(insight_card("Demands", result.get("demands", []), "◆"), unsafe_allow_html=True)
        c2.markdown(insight_card("Likes", result.get("likes", []), "◆"), unsafe_allow_html=True)
        c3.markdown(insight_card("Dislikes", result.get("dislikes", []), "◆"), unsafe_allow_html=True)
        c4.markdown(insight_card("Trending Topics", result.get("trends", []), "◆"), unsafe_allow_html=True)

        st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)

        section_header("Company Intelligence", "What the company is communicating — from video titles and descriptions")
        c5, c6, c7, c8 = st.columns(4)
        c5.markdown(insight_card("Launches", result.get("launches", []), "▸"), unsafe_allow_html=True)
        c6.markdown(insight_card("Announcements", result.get("announcements", []), "▸"), unsafe_allow_html=True)
        c7.markdown(insight_card("Focus Areas", result.get("focus_areas", []), "▸"), unsafe_allow_html=True)
        c8.markdown(insight_card("Campaigns", result.get("campaigns", []), "▸"), unsafe_allow_html=True)

        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        with st.expander("Analysis Details"):
            st.markdown(
                f"- **{result.get('analyzed_comments', 0):,}** YouTube comments (prioritized by engagement)\n"
                f"- **{result.get('analyzed_posts', 0):,}** video titles & descriptions\n"
                f"- Brand: `{metadata.get('category')}` · Date: `{metadata.get('date_from')} → {metadata.get('date_to')}`\n"
                f"- Started At: `{to_local_time(metadata.get('started_at'), '%b %d, %Y, %H:%M:%S')}`\n"
                f"- Model: Qwen 2.5 (7B) via Ollama · Map-reduce pipeline"
            )
else:
    if not active_job:
        st.markdown(f"""
        <div style="text-align:center;padding:80px 0;max-width:480px;margin:0 auto;">
            <div style="font-size:48px;margin-bottom:20px;opacity:0.6">◈</div>
            <div style="font-size:18px;font-weight:600;color:{TEXT_PRIMARY};margin-bottom:12px">
                Generate AI-Powered Insights
            </div>
            <p style="font-size:14px;color:{TEXT_MUTED};line-height:1.6">
                Select a brand and date range, then click <strong>Generate Analysis</strong>.
                The AI reads all YouTube comments and video descriptions to provide
                Customer Intelligence and Company Intelligence perspectives.
            </p>
            <p style="font-size:13px;color:{TEXT_MUTED};margin-top:16px">
                💬 Need a quick answer? Use the chat button in the bottom-right corner.
            </p>
        </div>
        """, unsafe_allow_html=True)

# 8. Loop Polling for Active Jobs
if active_job:
    import time
    time.sleep(2)
    st.rerun()

# Floating chat widget
floating_chat()
