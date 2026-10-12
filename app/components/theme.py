"""Quiet, editorial styling for the IAMP Streamlit interface."""
import streamlit as st


def apply_theme() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Libre+Baskerville:wght@400;700&display=swap');
    :root { --ink: #26332b; --muted: #6d776f; --accent: #506c55; --paper: #faf9f5; --line: #e4e6df; }
    html, body, [class*="css"], [data-testid="stApp"] { font-family: 'DM Sans', sans-serif; }
    [data-testid="stAppViewContainer"] { background: var(--paper); color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(250,249,245,.94); }
    [data-testid="stSidebar"] { background: #f0f2ec; border-right: 1px solid var(--line); }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: var(--muted); }
    .block-container { max-width: 1120px; padding-top: 2.8rem; padding-bottom: 4rem; }
    h1, h2 { font-family: 'Libre Baskerville', Georgia, serif !important; font-weight: 400 !important; letter-spacing: -.035em !important; color: var(--ink) !important; }
    h1 { font-size: clamp(2rem, 3.1vw, 2.8rem) !important; line-height: 1.25 !important; margin-bottom: .45rem !important; }
    h2 { font-size: 1.55rem !important; }
    h3 { font-size: 1.1rem !important; color: var(--ink) !important; }
    p, label, span { letter-spacing: 0; }
    [data-testid="stCaptionContainer"] { color: var(--muted); }
    [data-testid="stMetric"] { background: white; border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    [data-testid="stMetricValue"] { color: var(--ink); font-size: 1.7rem; }
    [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] > div:has(> [data-testid="stVerticalBlock"]) { border-radius: 14px; }
    [data-testid="stForm"] { background: white; border: 1px solid var(--line); padding: 22px; }
    [data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-baseweb="select"] > div { background: white !important; border-color: #d9dfd6 !important; border-radius: 9px !important; }
    [data-testid="stTextArea"] textarea:focus, [data-testid="stTextInput"] input:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 1px var(--accent) !important; }
    [data-testid="stButton"] button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] { background: var(--accent) !important; color: white !important; border: 1px solid var(--accent) !important; border-radius: 9px !important; font-weight: 600; }
    [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button { border-radius: 9px !important; }
    [data-testid="stExpander"] { background: white; border: 1px solid var(--line); border-radius: 12px; }
    [data-testid="stAlert"] { border-radius: 10px; }
    hr { border-color: var(--line) !important; margin: 1.6rem 0 !important; }
    .iamp-brand { padding: 4px 0 18px; }
    .iamp-wordmark { font-family: 'Libre Baskerville', Georgia, serif; font-size: 1.65rem; letter-spacing: -.05em; color: var(--ink); }
    .iamp-tagline { font-size: .78rem; line-height: 1.5; color: var(--muted); margin-top: 6px; }
    .iamp-footer { color: var(--muted); font-size: .75rem; padding-top: 12px; }
    @media (max-width: 700px) { .block-container { padding-top: 1.4rem; } [data-testid="stForm"] { padding: 14px; } }
    </style>
    """, unsafe_allow_html=True)
