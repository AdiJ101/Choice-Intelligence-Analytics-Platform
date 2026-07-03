import streamlit as st
import pandas as pd
from datetime import date, timedelta
import plotly.graph_objects as go
from api_client import client
from styles import inject_css, section_header, floating_chat

st.set_page_config(page_title="Content Explorer | Choice Intelligence", layout="wide", initial_sidebar_state="expanded")
inject_css()

# Data fetching
categories_data = client.get_categories()
categories = ["All Brands"] + [c["category_name"] for c in categories_data]

st.markdown("<h1>Content Explorer</h1>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 1. Filters & Search
# -----------------------------------------------------------------------------
with st.container():
    st.markdown("<div class='glass-card' style='padding: 16px; margin-bottom: 24px;'>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([2, 1, 1.5])
    with col1:
        search_query = st.text_input("Search", placeholder="Search for video detail...", label_visibility="collapsed")
    with col2:
        brand = st.selectbox("Brand", categories, label_visibility="collapsed")
    with col3:
        date_range = st.date_input("Date Range", value=[], label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

cat_filter = None if brand == "All Brands" else brand
d_from, d_to = None, None
if len(date_range) == 2:
    d_from, d_to = date_range

posts_response = client.get_posts(category=cat_filter, date_from=d_from, date_to=d_to, limit=10)
posts = posts_response.get("data", [])

if "selected_post_id" not in st.session_state:
    st.session_state.selected_post_id = None

# -----------------------------------------------------------------------------
# 2. Content Table
# -----------------------------------------------------------------------------
if posts:
    st.markdown("<div class='glass-card' style='padding:0;'>", unsafe_allow_html=True)
    # Header
    cols = st.columns([4, 1, 1.5, 1.5, 1.5, 1])
    cols[0].markdown("**VIDEO**")
    cols[1].markdown("**PLATFORM**")
    cols[2].markdown("**DATE**")
    cols[3].markdown("**VIEWS**")
    cols[4].markdown("**ENGAGEMENT**")
    cols[5].markdown("**ACTION**")
    
    for p in posts:
        pid = p["post_id"]
        title = p.get("title", "Unknown")
        platform = p.get("platform_display_name", "Unknown").capitalize()
        dt = p.get("publish_timestamp", "").split("T")[0] if p.get("publish_timestamp") else "N/A"
        views = p.get("latest_views", 0)
        likes = p.get("latest_likes", 0)
        comments = p.get("latest_comments", 0)
        engagement = ((likes + comments) / views * 100) if views > 0 else 0.0
        
        c = st.columns([4, 1, 1.5, 1.5, 1.5, 1])
        c[0].markdown(f"<div style='font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{title}</div>", unsafe_allow_html=True)
        c[1].markdown(f"<div style='font-size:14px;'>{platform}</div>", unsafe_allow_html=True)
        c[2].markdown(f"<div style='font-size:14px;color:#64748b;'>{dt}</div>", unsafe_allow_html=True)
        c[3].markdown(f"<div style='font-size:14px;'>{views:,}</div>", unsafe_allow_html=True)
        c[4].markdown(f"<div style='font-size:14px;'>{engagement:.1f}%</div>", unsafe_allow_html=True)
        if c[5].button("View", key=f"view_{pid}"):
            st.session_state.selected_post_id = pid
            st.rerun()
            
    st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("No videos found matching your criteria.")

# -----------------------------------------------------------------------------
# 3. Video Detail View
# -----------------------------------------------------------------------------
if st.session_state.selected_post_id:
    st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
    post_detail = client.get_post_detail(st.session_state.selected_post_id)
    if not post_detail.get("error"):
        data = post_detail
        p_title = data.get("title", "Unknown")
        p_views = data.get("latest_views", 0)
        p_likes = data.get("latest_likes", 0)
        p_comments = data.get("latest_comments", 0)
        p_eng = ((p_likes + p_comments) / p_views * 100) if p_views > 0 else 0.0
        
        st.markdown(f"""
        <div class="glass-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-size:13px; color:#64748b;">Video nam</div>
                    <h2 style="margin-top:0;">{p_title}</h2>
                </div>
                <div style="display:flex; gap: 40px; text-align:right;">
                    <div>
                        <div style="font-size:13px; color:#64748b;">Total Views</div>
                        <div style="font-size:24px; font-weight:700;">{p_views/1_000_000 if p_views > 1000000 else p_views/1000:.1f}M</div>
                    </div>
                    <div>
                        <div style="font-size:13px; color:#64748b;">Engagement</div>
                        <div style="font-size:24px; font-weight:700;">{p_eng:.1f}%</div>
                    </div>
                </div>
            </div>
            
            <div style="display:flex; gap:20px; margin-top:20px;">
                <div style="flex:1; background: linear-gradient(135deg, #eff6ff, #dbeafe); padding: 20px; border-radius:16px;">
                    <div style="font-size:14px; font-weight:600; margin-bottom:10px;">Overall Views</div>
                    <div style="font-size:28px; font-weight:800;">{p_views:,}</div>
                </div>
                <div style="flex:1; background: linear-gradient(135deg, #faf5ff, #f3e8ff); padding: 20px; border-radius:16px;">
                    <div style="font-size:14px; font-weight:600; margin-bottom:10px;">Overall Likes</div>
                    <div style="font-size:28px; font-weight:800; color:#7c3aed;">{p_likes:,}</div>
                </div>
                <div style="flex:1; background: linear-gradient(135deg, #fdf2f8, #fbcfe8); padding: 20px; border-radius:16px;">
                    <div style="font-size:14px; font-weight:600; margin-bottom:10px;">Total Comments</div>
                    <div style="font-size:28px; font-weight:800; color:#db2777;">{p_comments:,}</div>
                </div>
            </div>
            
            <div style="text-align:right; margin-top:20px;">
        """, unsafe_allow_html=True)
        
        if st.button("Close Details"):
            st.session_state.selected_post_id = None
            st.rerun()
            
        st.markdown("</div></div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. Scraper Status
# -----------------------------------------------------------------------------
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown("<h3>Scraper Status</h3>", unsafe_allow_html=True)

col_s1, col_s2 = st.columns([1, 2])
with col_s1:
    st.markdown("<p style='color:#64748b; font-size:14px;'>Real-time overview of the scraper's status and detailed logs.</p>", unsafe_allow_html=True)

with col_s2:
    status_data = client.get_scraper_status()
    s = status_data.get("status", "unknown")
    last = status_data.get("last_scrape", "N/A")
    next_s = status_data.get("next_scrape", "N/A")
    
    st.markdown(f"""
    <div style="display:flex; gap:16px;">
        <div class="glass-card" style="flex:1; padding:16px;">
            <div style="font-size:12px; font-weight:600; color:#64748b; text-transform:uppercase;">Status</div>
            <div style="font-size:20px; font-weight:700; display:flex; align-items:center; gap:8px;">
                <span style="color: {'#10b981' if s == 'running' else '#f59e0b'}; font-size:24px;">●</span> {s.title()}
            </div>
        </div>
        <div class="glass-card" style="flex:1; padding:16px;">
            <div style="font-size:12px; font-weight:600; color:#64748b; text-transform:uppercase;">Last Scrape</div>
            <div style="font-size:16px; font-weight:700;">{last}</div>
        </div>
        <div class="glass-card" style="flex:1; padding:16px;">
            <div style="font-size:12px; font-weight:600; color:#64748b; text-transform:uppercase;">Next Scrape</div>
            <div style="font-size:16px; font-weight:700;">{next_s}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    c_btn1, c_btn2, c_btn3 = st.columns(3)
    if c_btn1.button("Stop Scraper", use_container_width=True):
        client.send_scraper_command("stop")
        st.success("Sent STOP command.")
        st.rerun()
    if c_btn2.button("Run Now", use_container_width=True):
        client.send_scraper_command("start")
        st.success("Sent START command.")
        st.rerun()
    if c_btn3.button("Refresh", use_container_width=True):
        st.rerun()

floating_chat()
