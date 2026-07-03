import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
from api_client import client
from styles import inject_css, gradient_header, aesthetic_metric_card, section_header, floating_chat

st.set_page_config(page_title="Statistics | Choice Intelligence", layout="wide", initial_sidebar_state="expanded")
inject_css()

# Data fetching
overview = client.get_overview()
if "data" in overview: overview = overview["data"] # Handle case where it might be wrapped
categories_data = client.get_categories()
categories = ["All Brands"] + [c["category_name"] for c in categories_data]

# -----------------------------------------------------------------------------
# 1. Executive Summary
# -----------------------------------------------------------------------------
gradient_header("Statistics", "Executive Summary Across All Choice Group Brands")

# Mock average watch time as the backend doesn't provide it natively
avg_watch_time = "04:18"
avg_watch_delta = "↑ 8.1%"

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.markdown(aesthetic_metric_card("Total Videos", f"{overview.get('total_posts', 0):,}", "↑ 15.2%"), unsafe_allow_html=True)
with col2:
    st.markdown(aesthetic_metric_card("Total Comments", f"{overview.get('total_comments', 0):,}", "↑ 22.4%"), unsafe_allow_html=True)
with col3:
    st.markdown(aesthetic_metric_card("Total Likes", f"{overview.get('total_likes', 0):,}", "↑ 18.6%"), unsafe_allow_html=True)
with col4:
    st.markdown(aesthetic_metric_card("Total Views", f"{overview.get('total_views', 0):,}", "↑ 11.5%"), unsafe_allow_html=True)
with col5:
    st.markdown(aesthetic_metric_card("Avg Watch Time", avg_watch_time, avg_watch_delta), unsafe_allow_html=True)

st.markdown("<div style='height: 60px;'></div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. Most Viewed Videos
# -----------------------------------------------------------------------------
st.markdown("### Most Viewed Videos")
colA, colB = st.columns([3, 1])
with colB:
    days_filter = st.radio("Timeframe", ["Last 7 Days", "Last 30 Days"], horizontal=True, label_visibility="collapsed")
    brand_filter_1 = st.selectbox("Brand Filter 1", categories, key="brand1", label_visibility="collapsed")

days = 7 if days_filter == "Last 7 Days" else 30
date_from = date.today() - timedelta(days=days)
selected_cat_1 = None if brand_filter_1 == "All Brands" else brand_filter_1

top_posts_data = client.get_top_posts(limit=10, category=selected_cat_1, date_from=date_from).get("data", [])
if top_posts_data:
    df_top = pd.DataFrame(top_posts_data)
    df_top = df_top.sort_values(by="total_engagement", ascending=True) # Ascending for horizontal bar
    
    fig = go.Figure(go.Bar(
        x=df_top["total_engagement"],
        y=df_top["title"].str.slice(0, 40) + "...",
        orientation='h',
        marker=dict(color="#7c3aed", opacity=0.85, line=dict(width=0)),
        text=df_top["total_engagement"].apply(lambda x: f"{x:,}"),
        textposition="outside",
        textfont=dict(color="#0f172a", size=13)
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=400,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=13, color="#334155")),
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
else:
    st.info("No videos found for this timeframe.")

st.markdown("<hr>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. Brand Comparison & Top Performing Content
# -----------------------------------------------------------------------------
colL, colR = st.columns(2)

with colL:
    st.markdown("### Brand Comparison")
    brand_filter_2 = st.selectbox("Brand Filter 2", categories, key="brand2", label_visibility="collapsed")
    selected_cat_2 = None if brand_filter_2 == "All Brands" else brand_filter_2
    
    cat_analytics = client.get_by_category().get("data", [])
    if cat_analytics:
        df_cat = pd.DataFrame(cat_analytics)
        if selected_cat_2:
            df_cat = df_cat[df_cat['category_name'] == selected_cat_2]
            
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(name='Videos', x=df_cat['category_name'], y=df_cat['post_count'], marker_color='#a78bfa'))
        fig2.add_trace(go.Bar(name='Views', x=df_cat['category_name'], y=df_cat['total_views'], marker_color='#7dd3fc'))
        fig2.add_trace(go.Bar(name='Likes', x=df_cat['category_name'], y=df_cat['total_likes'], marker_color='#f472b6'))
        fig2.add_trace(go.Bar(name='Comments', x=df_cat['category_name'], y=df_cat['total_comments'], marker_color='#34d399'))
        
        fig2.update_layout(
            barmode='group',
            height=350,
            margin=dict(l=0, r=0, t=30, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.05)")
        )
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

with colR:
    st.markdown("### Top Performing Content")
    brand_filter_3 = st.selectbox("Brand Filter 3", categories, key="brand3", label_visibility="collapsed")
    selected_cat_3 = None if brand_filter_3 == "All Brands" else brand_filter_3
    
    top_perf_data = client.get_top_posts(limit=5, category=selected_cat_3).get("data", [])
    if top_perf_data:
        html = "<table style='width:100%; border-collapse: collapse; margin-top: 10px;'>"
        for i, post in enumerate(top_perf_data):
            num = i + 1
            title = post.get('title', 'Unknown Title')
            brand = post.get('category_name', 'Unknown Brand')
            views = post.get('total_engagement', 0)
            html += f'''<tr style="border-bottom: 1px solid rgba(0,0,0,0.05);">
<td style="padding: 12px 8px; width: 30px; font-weight: bold; color: #7c3aed;">{num}</td>
<td style="padding: 12px 8px;">
<div style="font-weight: 600; color: #0f172a; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 300px;">{title}</div>
<div style="font-size: 12px; color: #64748b;">{brand}</div>
</td>
<td style="padding: 12px 8px; text-align: right; font-weight: 600; color: #334155;">{views:,}</td>
</tr>'''
        html += "</table>"
        st.markdown(f"<div class='glass-card' style='padding:12px;'>{html}</div>", unsafe_allow_html=True)
    else:
        st.info("No content found.")

st.markdown("<hr>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. Brand Analytics
# -----------------------------------------------------------------------------
colX, colY = st.columns([3, 1])
with colX:
    st.markdown("### Brand Analytics")
with colY:
    brand_filter_4 = st.selectbox("Brand Filter 4", categories, key="brand4", label_visibility="collapsed")
selected_cat_4 = None if brand_filter_4 == "All Brands" else brand_filter_4

# Mini cards
c1, c2, c3, c4 = st.columns(4)
b_posts = overview.get('total_posts', 0)
b_views = overview.get('total_views', 0)
b_likes = overview.get('total_likes', 0)
b_comments = overview.get('total_comments', 0)
if selected_cat_4:
    # Filter stats if brand is selected
    cat_row = next((c for c in client.get_by_category().get("data", []) if c["category_name"] == selected_cat_4), None)
    if cat_row:
        b_posts = cat_row.get("post_count", 0)
        b_views = cat_row.get("total_views", 0)
        b_likes = cat_row.get("total_likes", 0)
        b_comments = cat_row.get("total_comments", 0)

with c1: st.markdown(aesthetic_metric_card("Total Videos", f"{b_posts:,}", "", "white"), unsafe_allow_html=True)
with c2: st.markdown(aesthetic_metric_card("Total Views", f"{b_views:,}", "", "white"), unsafe_allow_html=True)
with c3: st.markdown(aesthetic_metric_card("Total Likes", f"{b_likes:,}", "", "white"), unsafe_allow_html=True)
with c4: st.markdown(aesthetic_metric_card("Avg Watch Time", "04:18", "", "white"), unsafe_allow_html=True)



floating_chat()
