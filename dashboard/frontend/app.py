"""
dashboard/frontend/app.py — Landing page for Choice Intelligence Platform.
Blue & White design with animations.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
from dashboard.frontend.styles import (
    inject_css, navbar, floating_chat,
    ACCENT, ACCENT_DARK, ACCENT_LIGHT, ACCENT_BG,
    TEXT_PRIMARY, TEXT_MUTED, TEXT_SECONDARY,
    CARD_BG, BORDER, SHADOW, SHADOW_MD, RADIUS,
)

st.set_page_config(
    page_title="Choice Intelligence Platform",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_css()
navbar("home")

# ---------------------------------------------------------------------------
# Hero section with blue gradient
# ---------------------------------------------------------------------------
st.markdown(f"""
<div style="
    padding:48px 40px;
    margin:-24px -48px 32px -48px;
    background:linear-gradient(135deg, #0f1629 0%, #1a2b5f 40%, {ACCENT} 100%);
    border-radius:0 0 24px 24px;
    position:relative;
    overflow:hidden;
    animation:fadeIn 0.6s ease-out;
">
    <div style="position:absolute;top:0;left:0;right:0;bottom:0;background:radial-gradient(circle at 80% 20%, rgba(99, 102, 241, 0.15) 0%, transparent 50%);pointer-events:none"></div>
    <div style="position:relative;z-index:1">
        <div style="
            font-size:12px;font-weight:600;color:rgba(255,255,255,0.6);
            text-transform:uppercase;letter-spacing:0.12em;margin-bottom:16px;
            animation:fadeInUp 0.5s ease-out 0.1s both;
        ">
            Choice Intelligence Platform
        </div>
        <h1 style="
            font-size:44px;font-weight:900;color:white;
            letter-spacing:-0.03em;margin:0 0 16px 0;line-height:1.1;
            animation:fadeInUp 0.5s ease-out 0.2s both;
        ">
            Customer & Content<br>Intelligence
        </h1>
        <p style="
            font-size:16px;color:rgba(255,255,255,0.75);
            max-width:560px;line-height:1.6;margin:0;
            animation:fadeInUp 0.5s ease-out 0.3s both;
        ">
            AI-powered analytics for Choice Group's YouTube presence. Discover insights 
            across all brands powered by local AI.
        </p>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Navigation cards
# ---------------------------------------------------------------------------

def nav_card(title: str, description: str, icon: str, delay: float):
    return f"""
    <div style="
        background:{CARD_BG};
        border:1px solid {BORDER};
        border-radius:{RADIUS};
        padding:28px 24px;
        box-shadow:{SHADOW};
        height:100%;
        transition:all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        cursor:pointer;
        animation:fadeInUp 0.5s ease-out {delay}s both;
    " onmouseover="this.style.boxShadow='{SHADOW_MD}';this.style.transform='translateY(-4px)';this.style.borderColor='{ACCENT}50'"
      onmouseout="this.style.boxShadow='{SHADOW}';this.style.transform='translateY(0)';this.style.borderColor='{BORDER}'">
        <div style="
            width:40px;height:40px;border-radius:10px;
            background:linear-gradient(135deg, {ACCENT_LIGHT}, {ACCENT}15);
            display:flex;align-items:center;justify-content:center;
            font-size:18px;margin-bottom:16px;color:{ACCENT};font-weight:700;
        ">{icon}</div>
        <div style="font-size:16px;font-weight:700;color:{TEXT_PRIMARY};margin-bottom:8px;letter-spacing:-0.01em">{title}</div>
        <div style="font-size:13px;color:{TEXT_MUTED};line-height:1.5">{description}</div>
    </div>
    """

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(nav_card(
        "Overview", "Executive summary with key metrics, trends, and top content.", "◆", 0.1
    ), unsafe_allow_html=True)

with col2:
    st.markdown(nav_card(
        "Statistics", "Explore videos, drill into details, and compare brand performance.", "◇", 0.15
    ), unsafe_allow_html=True)

with col3:
    st.markdown(nav_card(
        "AI Analytics", "Customer + Company insights, plus a chatbot for Q&A over your content.", "◈", 0.2
    ), unsafe_allow_html=True)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

col4, col5, col6 = st.columns(3)

with col4:
    st.markdown(f"""
    <div style="
        background:linear-gradient(135deg, {ACCENT}08, {ACCENT}04);
        border:1px solid {ACCENT}25;
        border-radius:{RADIUS};
        padding:28px 24px;
        height:100%;
        animation:fadeInUp 0.5s ease-out 0.25s both;
    ">
        <div style="
            width:40px;height:40px;border-radius:10px;
            background:linear-gradient(135deg, {ACCENT}, {ACCENT_DARK});
            display:flex;align-items:center;justify-content:center;
            font-size:16px;margin-bottom:16px;color:white;
        ">⚡</div>
        <div style="font-size:16px;font-weight:700;color:{TEXT_PRIMARY};margin-bottom:8px">Powered Locally</div>
        <div style="font-size:13px;color:{TEXT_MUTED};line-height:1.5">
            Qwen 2.5 (7B) via Ollama. No cloud APIs. No data leaves your machine.
        </div>
    </div>
    """, unsafe_allow_html=True)

with col5:
    st.markdown(f"""
    <div style="
        background:linear-gradient(135deg, {ACCENT}08, {ACCENT}04);
        border:1px solid {ACCENT}25;
        border-radius:{RADIUS};
        padding:28px 24px;
        height:100%;
        animation:fadeInUp 0.5s ease-out 0.3s both;
    ">
        <div style="
            width:40px;height:40px;border-radius:10px;
            background:linear-gradient(135deg, {ACCENT}, {ACCENT_DARK});
            display:flex;align-items:center;justify-content:center;
            font-size:16px;margin-bottom:16px;color:white;
        ">🔒</div>
        <div style="font-size:16px;font-weight:700;color:{TEXT_PRIMARY};margin-bottom:8px">Multilingual</div>
        <div style="font-size:13px;color:{TEXT_MUTED};line-height:1.5">
            Understands Hindi, Marathi, Hinglish, and English content — answers in English.
        </div>
    </div>
    """, unsafe_allow_html=True)

with col6:
    st.markdown(f"""
    <div style="
        background:linear-gradient(135deg, {ACCENT}08, {ACCENT}04);
        border:1px solid {ACCENT}25;
        border-radius:{RADIUS};
        padding:28px 24px;
        height:100%;
        animation:fadeInUp 0.5s ease-out 0.35s both;
    ">
        <div style="
            width:40px;height:40px;border-radius:10px;
            background:linear-gradient(135deg, {ACCENT}, {ACCENT_DARK});
            display:flex;align-items:center;justify-content:center;
            font-size:16px;margin-bottom:16px;color:white;
        ">💬</div>
        <div style="font-size:16px;font-weight:700;color:{TEXT_PRIMARY};margin-bottom:8px">Ask Anytime</div>
        <div style="font-size:13px;color:{TEXT_MUTED};line-height:1.5">
            Use the floating chat button in the bottom-right corner on any page.
        </div>
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("<div style='height:48px'></div>", unsafe_allow_html=True)
st.markdown(f"""
<div style="text-align:center;padding:24px 0;border-top:1px solid {BORDER};animation:fadeIn 0.8s ease-out">
    <span style="font-size:12px;color:{TEXT_MUTED};letter-spacing:0.02em">
        Choice Intelligence Platform · YouTube Analytics · Built for Choice Group
    </span>
</div>
""", unsafe_allow_html=True)

# Floating chat widget
floating_chat()
