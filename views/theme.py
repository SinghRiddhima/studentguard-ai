"""Shared appearance for the Streamlit shell."""
import streamlit as st

PALETTES = {
    "dark": ("#08090D", "#141722", "#252938", "#F5F7FF", "#B5BCD2", "#9B5CFF", "#42E8FF", "#FF4FD8"),
    "light": ("#F7F8FC", "#FFFFFF", "#E4E7F0", "#171824", "#535B70", "#7546E8", "#078DA8", "#B42996"),
}


def apply():
    choice = st.query_params.get("theme", st.session_state.get("sg_theme", "dark"))
    choice = choice if choice in PALETTES else "dark"
    st.session_state["sg_theme"] = choice
    bg, surface, border, text, muted, violet, cyan, magenta = PALETTES[choice]
    layout = """
    html:has(.sg-shell) {color-scheme: var(--sg-scheme);}
    [data-testid="stAppViewContainer"], [data-testid="stApp"], [data-testid="stHeader"] {
      background: var(--sg-bg); color: var(--sg-text);
    }
    [data-testid="stSidebar"], [data-testid="stSidebarContent"],
    [data-testid="stForm"], [data-testid="stFileUploaderDropzone"],
    [data-testid="stVerticalBlockBorderWrapper"] > div,
    [data-baseweb="popover"] [role="listbox"], [data-testid="stDataFrame"] {
      background-color: var(--sg-surface); color: var(--sg-text); border-color: var(--sg-border);
    }
    [data-testid="stApp"] :is(h1,h2,h3,h4,label), [data-testid="stSidebarNav"] a,
    [data-testid="stWidgetLabel"], [data-testid="stCaptionContainer"] {
      color: var(--sg-text);
    }
    [data-testid="stApp"] :is([data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"] > div),
    [data-testid="stApp"] :is(button[kind="secondary"],button[kind="secondaryFormSubmit"],[role="tab"]),
    [data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapsedControl"] {
      color: var(--sg-text); background: var(--sg-surface); border-color: var(--sg-border);
    }
    [data-testid="stApp"] :is(input,textarea)::placeholder {color: var(--sg-muted);}
    [data-testid="stApp"] :is([data-baseweb="select"],[data-baseweb="input"]) svg {
      color: var(--sg-text); fill: currentColor;
    }
    [data-testid="stApp"] :is(input,textarea), [data-baseweb="popover"] [role="option"] {
      color: var(--sg-text); caret-color: var(--sg-text);
    }
    [data-testid="stApp"] button:is([kind="primary"],[kind="primaryFormSubmit"]) {
      background: var(--sg-violet); border-color: var(--sg-violet); color: var(--sg-on-accent);
    }
    [data-testid="stApp"] :focus-visible {outline: 2px solid var(--sg-cyan); outline-offset: 3px;}
    .sg-wordmark {font-weight:750; letter-spacing:.04em; color:var(--sg-text); padding:.4rem 0;}
    .sg-landing {min-height: 430px; display:grid; grid-template-columns:1.2fr 1fr; align-items:center;
      gap:2rem; position:relative; overflow:hidden; isolation:isolate; border:1px solid var(--sg-border);
      border-radius: 28px; padding:clamp(1.5rem,5vw,4.2rem);
      background: radial-gradient(ellipse at 86% 38%,color-mix(in srgb,var(--sg-violet) 15%,transparent),transparent 62%),var(--sg-surface);
    }
    .sg-landing h1 {font-size:clamp(2.5rem,5.2vw,5.25rem); line-height:1.02; letter-spacing:-.067em; padding:.75rem 0;}
    .sg-landing p {color:var(--sg-muted); font-size:1.07rem; max-width:37ch;}
    .sg-eyebrow {font-size:.71rem; letter-spacing:.16em; color:var(--sg-eyebrow); font-weight:750;}
    .sg-orbit {position:relative; width:100%; max-width:385px; aspect-ratio:1; justify-self:center;
      display:grid; place-items:center; pointer-events:none;}
    .sg-orbit-core {width:46%; aspect-ratio:1; border-radius:50%; background:
      radial-gradient(circle at 34% 28%,#d8f8ff 0, var(--sg-cyan) 5%,var(--sg-violet) 27%,#27154b 54%,#0a0914 77%);
      box-shadow:0 0 55px color-mix(in srgb,var(--sg-violet) 60%,transparent), inset -12px -8px 26px #090812;
    }
    .sg-orbit-ring {position:absolute; width:93%; height:50%; border:1px solid var(--sg-violet);
      border-radius:50%; transform:rotate(var(--tilt)); box-shadow:0 0 17px color-mix(in srgb,var(--sg-violet) 30%,transparent);}
    .sg-orbit-ring:nth-child(2) {border-color:var(--sg-cyan); width:83%;}
    .sg-orbit-ring:nth-child(3) {border-color:var(--sg-magenta); height:42%;}
    .sg-orbit-ring::after {content:""; position:absolute; left:5%; top:19%; width:.55rem; aspect-ratio:1;
      border-radius:50%; background:var(--sg-cyan); box-shadow:0 0 14px var(--sg-cyan);
      animation:sg-glow 5s ease-in-out infinite alternate;}
    @keyframes sg-glow {to {opacity:.4; scale:.7;}}
    @media (max-width:700px) {
      .sg-landing {grid-template-columns:1fr; gap:.5rem; min-height:0;}
      .sg-orbit {max-width:230px;}
    }
    @media (prefers-reduced-motion:reduce) {
      .sg-orbit-ring::after {animation:none;}
      html:has(.sg-shell) * {scroll-behavior:auto !important;}
    }
    """
    tokens = f"""
    :root {{ --sg-bg:{bg}; --sg-surface:{surface}; --sg-border:{border};
      --sg-text:{text}; --sg-muted:{muted}; --sg-violet:{violet}; --sg-cyan:{cyan};
      --sg-magenta:{magenta}; --sg-scheme:{choice};
      --sg-eyebrow:{cyan if choice == "dark" else "#06677E"};
      --sg-on-accent:{"#08090D" if choice == "dark" else "#FFFFFF"}; }}
    """
    st.html(f'<style>{tokens}{layout}</style><span class="sg-shell" hidden></span>')


def toggle():
    current = st.session_state["sg_theme"]
    alternate = "light" if current == "dark" else "dark"
    if st.button(f"{alternate.title()} mode", key="sg_theme_toggle"):
        st.session_state["sg_theme"] = alternate
        st.query_params["theme"] = alternate
        st.rerun()
