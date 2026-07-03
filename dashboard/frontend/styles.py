"""
dashboard/frontend/styles.py — Design system: Aesthetic Light Mode.
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------

ACCENT       = "#7c3aed" # Vibrant purple
ACCENT_DARK  = "#5b21b6"
ACCENT_LIGHT = "#f3e8ff"
ACCENT_BG    = "#faf5ff"
BG           = "#f8fafc"
CARD_BG      = "rgba(255, 255, 255, 0.7)"
BORDER       = "rgba(255, 255, 255, 0.5)"
TEXT_PRIMARY  = "#0f172a"
TEXT_SECONDARY = "#334155"
TEXT_MUTED    = "#64748b"
SHADOW       = "0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01)"
SHADOW_MD    = "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.05)"
SHADOW_LG    = "0 25px 50px -12px rgba(0, 0, 0, 0.15)"
RADIUS       = "16px"
RADIUS_SM    = "12px"

def inject_css():
    """Inject the global design system CSS."""
    st.markdown(_CSS, unsafe_allow_html=True)

def floating_chat(api_base: str = "http://localhost:8000"):
    """Inject a floating chat widget (FAB) into the parent document."""
    import streamlit.components.v1 as components

    widget_js = f"""
<script>
(function() {{
    const doc = window.parent.document;
    if (doc.getElementById('cig-chat-root')) return;

    const ACCENT = '{ACCENT}';
    const ACCENT_DARK = '{ACCENT_DARK}';
    const API = '{api_base}';

    const style = doc.createElement('style');
    style.textContent = `
        #cig-fab {{
            position: fixed; bottom: 24px; right: 24px; z-index: 2147483647;
            width: 60px; height: 60px; border-radius: 50%;
            background: linear-gradient(135deg, ${{ACCENT}}, ${{ACCENT_DARK}});
            box-shadow: 0 8px 24px rgba(124,58,237,0.35);
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; transition: transform .2s ease, box-shadow .2s ease;
            border: none;
        }}
        #cig-fab:hover {{ transform: scale(1.08); box-shadow: 0 12px 32px rgba(124,58,237,0.45); }}
        #cig-fab svg {{ width: 28px; height: 28px; fill: white; }}
        #cig-panel {{
            position: fixed; bottom: 96px; right: 24px; z-index: 2147483647;
            width: 380px; max-width: calc(100vw - 48px); height: 540px; max-height: calc(100vh - 140px);
            background: rgba(255,255,255,0.85); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255,255,255,0.4); border-radius: 20px;
            box-shadow: 0 24px 64px rgba(0,0,0,0.12);
            display: none; flex-direction: column; overflow: hidden;
            font-family: 'Inter', sans-serif;
            animation: cigUp .25s cubic-bezier(.4,0,.2,1);
        }}
        @keyframes cigUp {{ from {{ opacity:0; transform: translateY(16px); }} to {{ opacity:1; transform: translateY(0); }} }}
        #cig-panel.open {{ display: flex; }}
        #cig-head {{
            background: linear-gradient(135deg, ${{ACCENT}}, ${{ACCENT_DARK}}); color: white;
            padding: 16px 20px; display: flex; align-items: center; justify-content: space-between;
        }}
        #cig-head .t {{ font-size: 15px; font-weight: 700; }}
        #cig-head .s {{ font-size: 12px; opacity: .9; margin-top: 2px; }}
        #cig-close {{ cursor: pointer; font-size: 20px; line-height: 1; opacity: .85; background:none;border:none;color:white; }}
        #cig-close:hover {{ opacity: 1; }}
        #cig-msgs {{ flex: 1; overflow-y: auto; padding: 16px; background: transparent; }}
        .cig-msg {{ margin-bottom: 12px; display: flex; }}
        .cig-msg.u {{ justify-content: flex-end; }}
        .cig-bubble {{ max-width: 80%; padding: 10px 14px; border-radius: 14px; font-size: 13.5px; line-height: 1.5; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }}
        .cig-msg.u .cig-bubble {{ background: linear-gradient(135deg, ${{ACCENT}}, ${{ACCENT_DARK}}); color: white; border-bottom-right-radius: 4px; }}
        .cig-msg.b .cig-bubble {{ background: white; color: #0f172a; border: 1px solid #e2e8f0; border-bottom-left-radius: 4px; }}
        #cig-foot {{ padding: 12px; border-top: 1px solid rgba(255,255,255,0.4); background: rgba(255,255,255,0.6); display: flex; gap: 8px; }}
        #cig-input {{
            flex: 1; border: 1px solid #cbd5e1; border-radius: 12px; padding: 10px 12px;
            font-size: 13.5px; font-family: inherit; outline: none; resize: none; background: white;
        }}
        #cig-input:focus {{ border-color: ${{ACCENT}}; box-shadow: 0 0 0 3px rgba(124,58,237,.15); }}
        #cig-send {{
            background: linear-gradient(135deg, ${{ACCENT}}, ${{ACCENT_DARK}}); color: white; border: none;
            border-radius: 12px; padding: 0 16px; font-weight: 600; font-size: 13.5px; cursor: pointer;
            box-shadow: 0 2px 6px rgba(124,58,237,0.3);
        }}
        #cig-send:disabled {{ opacity: .5; cursor: not-allowed; }}
        .cig-typing {{ font-size: 13px; color: #64748b; font-style: italic; box-shadow:none !important; background:transparent !important; border:none !important; }}
        .cig-srcs {{ margin-top: 8px; font-size: 11px; color: #64748b; }}
        .cig-srcs summary {{ cursor: pointer; color: ${{ACCENT}}; font-weight: 600; }}
        #cig-msgs::-webkit-scrollbar {{ width: 6px; }}
        #cig-msgs::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 3px; }}
    `;
    doc.head.appendChild(style);

    const root = doc.createElement('div');
    root.id = 'cig-chat-root';
    root.innerHTML = `
        <button id="cig-fab" title="Ask AI">
            <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/></svg>
        </button>
        <div id="cig-panel">
            <div id="cig-head">
                <div>
                    <div class="t">Ask AI</div>
                    <div class="s">Grounded in your content data</div>
                </div>
                <button id="cig-close">&times;</button>
            </div>
            <div id="cig-msgs"></div>
            <div id="cig-foot">
                <textarea id="cig-input" rows="1" placeholder="Ask a question..."></textarea>
                <button id="cig-send">Send</button>
            </div>
        </div>
    `;
    doc.body.appendChild(root);

    const fab = doc.getElementById('cig-fab');
    const panel = doc.getElementById('cig-panel');
    const closeBtn = doc.getElementById('cig-close');
    const msgs = doc.getElementById('cig-msgs');
    const input = doc.getElementById('cig-input');
    const send = doc.getElementById('cig-send');

    let history = [];
    try {{ history = JSON.parse(window.parent.localStorage.getItem('cig_chat') || '[]'); }} catch(e) {{ history = []; }}

    function save() {{
        try {{ window.parent.localStorage.setItem('cig_chat', JSON.stringify(history.slice(-50))); }} catch(e) {{}}
    }}
    function esc(s) {{
        const d = doc.createElement('div'); d.textContent = s; return d.innerHTML;
    }}
    function render() {{
        if (history.length === 0) {{
            msgs.innerHTML = '<div style="text-align:center;color:#64748b;font-size:13px;padding:40px 16px">' +
                '👋 Ask me anything about your YouTube content — products, customer feedback, trends, and more.</div>';
            return;
        }}
        msgs.innerHTML = history.map(function(m) {{
            let srcs = '';
            if (m.sources && m.sources.length) {{
                srcs = '<details class="cig-srcs"><summary>Sources (' + m.sources.length + ')</summary>' +
                    m.sources.map(function(s, i) {{
                        return '<div style="margin-top:6px">' + (i+1) + '. <b>' + esc(s.category_name) + '</b> · ' +
                            esc(s.post_type) + ' (' + Math.round(s.score*100) + '%)<br>' +
                            esc((s.content_preview||'').slice(0,140)) + '...</div>';
                    }}).join('') + '</details>';
            }}
            return '<div class="cig-msg ' + (m.role === 'user' ? 'u' : 'b') + '">' +
                   '<div class="cig-bubble">' + esc(m.content).replace(/\\n/g,'<br>') + srcs + '</div></div>';
        }}).join('');
        msgs.scrollTop = msgs.scrollHeight;
    }}

    async function ask(q) {{
        history.push({{role:'user', content:q}}); save(); render();
        const typing = doc.createElement('div');
        typing.className = 'cig-msg b'; typing.id = 'cig-typing';
        typing.innerHTML = '<div class="cig-bubble cig-typing">Thinking...</div>';
        msgs.appendChild(typing); msgs.scrollTop = msgs.scrollHeight;
        send.disabled = true;
        try {{
            const r = await fetch(API + '/api/ask', {{
                method: 'POST', headers: {{'Content-Type':'application/json'}},
                body: JSON.stringify({{
                    question: q,
                    top_k: 8,
                    history: history.slice(-8).map(function(m) {{
                        return {{role: m.role === 'bot' ? 'assistant' : 'user', content: m.content}};
                    }})
                }})
            }});
            const data = await r.json();
            const t = doc.getElementById('cig-typing'); if (t) t.remove();
            if (data.error) {{
                history.push({{role:'bot', content: data.error}});
            }} else {{
                history.push({{role:'bot', content: data.answer || 'No answer.', sources: data.sources || []}});
            }}
        }} catch(e) {{
            const t = doc.getElementById('cig-typing'); if (t) t.remove();
            history.push({{role:'bot', content: 'Error: could not reach the AI service.'}});
        }}
        save(); render(); send.disabled = false;
    }}

    fab.addEventListener('click', function() {{
        panel.classList.toggle('open');
        if (panel.classList.contains('open')) {{ render(); input.focus(); }}
    }});
    closeBtn.addEventListener('click', function() {{ panel.classList.remove('open'); }});
    function doSend() {{
        const q = input.value.trim(); if (!q) return;
        input.value = ''; ask(q);
    }}
    send.addEventListener('click', doSend);
    input.addEventListener('keydown', function(e) {{
        if (e.key === 'Enter' && !e.shiftKey) {{ e.preventDefault(); doSend(); }}
    }});

    render();
}})();
</script>
"""
    components.html(widget_js, height=0)


def navbar(current_page: str = ""):
    """We no longer use a top navbar. Using Streamlit's native sidebar, styled via CSS."""
    pass


_CSS = f"""
<style>
/* ═══════════════════════════════════════════════════════════════════════════
   CHOICE INTELLIGENCE PLATFORM — Aesthetic Light Mode
   ═══════════════════════════════════════════════════════════════════════════ */

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* --- Animations --- */
@keyframes fadeInUp {{ from {{ opacity: 0; transform: translateY(16px); }} to {{ opacity: 1; transform: translateY(0); }} }}
@keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
@keyframes pageEnter {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
@keyframes gradientShift {{ 0% {{ background-position: 0% 50%; }} 50% {{ background-position: 100% 50%; }} 100% {{ background-position: 0% 50%; }} }}

/* --- Base --- */
html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, sans-serif !important;
}}

.stApp {{
    background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%) !important;
}}

/* Main container */
.main .block-container {{
    padding: 2rem 3rem 4rem 3rem !important;
    max-width: 1400px !important;
    animation: pageEnter 0.5s cubic-bezier(0.22, 1, 0.36, 1) !important;
}}

/* --- Sidebar Styling --- */
[data-testid="stSidebar"] {{
    background-color: rgba(241, 245, 249, 0.95) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.5) !important;
}}
[data-testid="stSidebarNav"] span {{
    font-weight: 600 !important;
    color: {TEXT_SECONDARY} !important;
}}
[data-testid="stSidebarNav"] div[data-testid="stSidebarNavItems"] a[aria-current="page"] {{
    background: linear-gradient(135deg, {ACCENT}, {ACCENT_DARK}) !important;
    border-radius: 12px !important;
    margin: 0 12px !important;
}}
[data-testid="stSidebarNav"] div[data-testid="stSidebarNavItems"] a[aria-current="page"] span {{
    color: white !important;
}}

/* --- Headers --- */
h1 {{
    font-size: 36px !important; font-weight: 800 !important; color: {TEXT_PRIMARY} !important;
    letter-spacing: -0.03em !important; margin-bottom: 0.25rem !important; animation: fadeInUp 0.5s ease-out !important;
}}
h2 {{
    font-size: 22px !important; font-weight: 700 !important; color: {TEXT_PRIMARY} !important;
    letter-spacing: -0.01em !important; margin-top: 1.5rem !important; animation: fadeInUp 0.4s ease-out !important;
}}
h3 {{ font-size: 17px !important; font-weight: 600 !important; color: {TEXT_PRIMARY} !important; }}

/* --- Glassmorphic Containers --- */
.glass-card {{
    background: {CARD_BG};
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
    padding: 24px;
    box-shadow: {SHADOW};
    transition: all 0.3s ease;
}}
.glass-card:hover {{
    box-shadow: {SHADOW_MD};
    transform: translateY(-2px);
}}

/* --- Native Streamlit Metric Cards override (if used) --- */
[data-testid="stMetric"] {{
    background: rgba(255,255,255,0.7) !important;
    backdrop-filter: blur(16px) !important;
    border: 1px solid rgba(255,255,255,0.8) !important;
    border-radius: {RADIUS} !important;
    padding: 24px !important;
    box-shadow: {SHADOW} !important;
    transition: all 0.3s ease !important;
    animation: fadeInUp 0.5s ease-out !important;
}}
[data-testid="stMetric"]:hover {{
    box-shadow: {SHADOW_MD} !important;
    transform: translateY(-2px) !important;
}}
[data-testid="stMetricLabel"] {{
    font-size: 13px !important; font-weight: 600 !important; color: {TEXT_SECONDARY} !important;
}}
[data-testid="stMetricValue"] {{
    font-size: 32px !important; font-weight: 800 !important; color: {TEXT_PRIMARY} !important;
}}

/* --- Buttons --- */
.stButton > button {{
    background: linear-gradient(135deg, {ACCENT}, {ACCENT_DARK}) !important;
    color: white !important; border: none !important; border-radius: 12px !important;
    padding: 0.5rem 1.2rem !important; font-weight: 600 !important; font-size: 14px !important;
    transition: all 0.2s ease !important; box-shadow: 0 4px 12px rgba(124, 58, 237, 0.2) !important;
}}
.stButton > button:hover {{
    box-shadow: 0 8px 24px rgba(124, 58, 237, 0.3) !important; transform: translateY(-2px) !important;
}}

/* --- DataFrames / Tables --- */
[data-testid="stDataFrame"] {{
    background: rgba(255,255,255,0.7) !important; backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255,255,255,0.8) !important; border-radius: {RADIUS} !important;
    overflow: hidden !important; box-shadow: {SHADOW} !important; animation: fadeInUp 0.5s ease-out !important;
}}
[data-testid="stDataFrame"] th {{
    background: rgba(243, 244, 246, 0.8) !important; font-weight: 600 !important; font-size: 12px !important;
    text-transform: uppercase !important; color: {TEXT_SECONDARY} !important; border-bottom: 1px solid #e2e8f0 !important;
}}
[data-testid="stDataFrame"] td {{ color: {TEXT_PRIMARY} !important; font-size: 14px !important; border-bottom: 1px solid rgba(255,255,255,0.3) !important; }}

/* --- Inputs --- */
[data-testid="stSelectbox"] > div > div, .stTextInput > div > div > input, [data-testid="stDateInput"] > div > div > input {{
    background: rgba(255,255,255,0.8) !important;
    border-radius: 12px !important; border-color: #cbd5e1 !important; font-size: 14px !important;
    transition: all 0.2s ease !important;
}}
[data-testid="stSelectbox"] > div > div:focus-within, .stTextInput > div > div > input:focus {{
    border-color: {ACCENT} !important; box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.15) !important;
}}

/* --- Expanders --- */
[data-testid="stExpander"] {{
    background: rgba(255,255,255,0.7) !important; backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255,255,255,0.8) !important; border-radius: {RADIUS} !important;
    box-shadow: {SHADOW} !important; transition: all 0.2s ease !important;
}}
[data-testid="stExpander"]:hover {{ box-shadow: {SHADOW_MD} !important; }}

/* --- Plotly --- */
[data-testid="stPlotlyChart"] {{
    background: rgba(255,255,255,0.7) !important; backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255,255,255,0.8) !important; border-radius: {RADIUS} !important;
    padding: 8px !important; box-shadow: {SHADOW} !important; transition: all 0.3s ease !important;
    animation: fadeInUp 0.5s ease-out !important; overflow: hidden !important;
}}
[data-testid="stPlotlyChart"]:hover {{ box-shadow: {SHADOW_MD} !important; }}

/* --- Scrollbar --- */
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 4px; }}
::-webkit-scrollbar-thumb:hover {{ background: #94a3b8; }}

/* --- Hide Streamlit Branding --- */
#MainMenu {{visibility: hidden;}} footer {{visibility: hidden;}} header {{visibility: hidden;}}
</style>
"""


def gradient_header(title: str, subtitle: str = ""):
    """Renders a beautiful gradient banner."""
    st.markdown(f"""
    <div style="
        background: linear-gradient(120deg, #d8b4fe 0%, #818cf8 50%, #60a5fa 100%);
        border-radius: 20px;
        padding: 40px 32px 100px 32px;
        margin-bottom: -60px;
        color: white;
        box-shadow: 0 10px 30px -10px rgba(99, 102, 241, 0.4);
        position: relative;
        overflow: hidden;
    ">
        <div style="position:relative; z-index:2;">
            <h1 style="color:white !important; margin:0; font-size:32px !important; letter-spacing:-0.02em !important; text-shadow: 0 2px 4px rgba(0,0,0,0.1);">{title}</h1>
            <p style="color:rgba(255,255,255,0.9); margin-top:8px; font-size:15px; font-weight:500;">{subtitle}</p>
        </div>
        <div style="position:absolute; top:-50%; right:-10%; width:400px; height:400px; background:radial-gradient(circle, rgba(255,255,255,0.3) 0%, transparent 70%); border-radius:50%;"></div>
    </div>
    """, unsafe_allow_html=True)


def aesthetic_metric_card(label: str, value: str, delta: str = "", gradient: str = "linear-gradient(135deg, rgba(255,255,255,0.9), rgba(248,250,252,0.8))") -> str:
    """A highly aesthetic glassmorphic metric card with custom inner gradient."""
    delta_html = ""
    if delta:
        color = "#10b981" if "+" in delta or "↑" in delta else "#ef4444"
        delta_html = f'<div style="font-size:13px;color:{color};font-weight:600;margin-top:8px">{delta}</div>'
    return f"""
    <div style="
        background: {gradient};
        border: 1px solid rgba(255,255,255,1);
        border-radius: 20px;
        padding: 24px;
        box-shadow: 0 8px 32px rgba(31, 38, 135, 0.05);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        position: relative;
        overflow: hidden;
        transition: all 0.3s ease;
        animation: fadeInUp 0.5s ease-out;
        z-index: 10;
        min-height: 140px;
    " onmouseover="this.style.transform='translateY(-4px)'; this.style.boxShadow='0 12px 40px rgba(31, 38, 135, 0.1)';"
      onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 8px 32px rgba(31, 38, 135, 0.05)';">
        <div style="font-size:13px;font-weight:600;color:#475569;margin-bottom:8px">{label}</div>
        <div style="font-size:32px;font-weight:800;color:#0f172a;letter-spacing:-0.02em">{value}</div>
        {delta_html}
    </div>
    """

def section_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<h2 style="margin-bottom:4px">{title}</h2>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<p style="font-size:14px;color:#64748b;margin:0 0 20px 0">{subtitle}</p>', unsafe_allow_html=True)

def insight_card(title: str, items: list[str], icon: str = "✨") -> str:
    items_html = ""
    if items:
        for i, item in enumerate(items):
            delay = i * 0.05
            items_html += (
                f'<li style="margin-bottom:10px;font-size:13px;color:#334155;'
                f'line-height:1.5;animation:fadeInUp 0.3s ease-out {delay}s both;'
                f'padding-left:16px;position:relative;">'
                f'<span style="position:absolute;left:0;top:6px;width:6px;height:6px;border-radius:50%;background:{ACCENT}"></span>{item}</li>'
            )
    else:
        items_html = f'<li style="color:#94a3b8;font-style:italic;font-size:13px;list-style:none">No signals detected</li>'

    return f"""
    <div class="glass-card" style="height:100%; border-radius:20px;">
        <div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:16px;display:flex;align-items:center;gap:8px;">
            <span style="background:{ACCENT_LIGHT};color:{ACCENT};width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;">{icon}</span> 
            {title}
        </div>
        <ul style="margin-top:0;padding-left:0;list-style:none">
            {items_html}
        </ul>
    </div>
    """
