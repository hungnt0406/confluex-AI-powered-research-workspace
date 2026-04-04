"""
LitReview AI — Automated Literature Review System
Streamlit entry point.
"""

import streamlit as st
from src.db.session import init_db
from src.auth.auth_manager import ensure_admin_exists, require_auth, logout


# --- Page Config ---
st.set_page_config(
    page_title="LitReview AI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .main-title {
        background: linear-gradient(135deg, #6C63FF 0%, #9D4EDD 50%, #E040FB 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0;
    }

    .subtitle {
        color: #888;
        font-size: 1.1rem;
        margin-top: 0;
    }

    .stat-card {
        background: linear-gradient(135deg, #1A1D29 0%, #252836 100%);
        border: 1px solid rgba(108, 99, 255, 0.2);
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        transition: transform 0.2s, border-color 0.2s;
    }

    .stat-card:hover {
        transform: translateY(-2px);
        border-color: rgba(108, 99, 255, 0.5);
    }

    .stat-number {
        font-size: 2rem;
        font-weight: 700;
        color: #6C63FF;
    }

    .stat-label {
        font-size: 0.85rem;
        color: #888;
        margin-top: 0.25rem;
    }

    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0E1117 0%, #1A1D29 100%);
    }

    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.2s;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(108, 99, 255, 0.3);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- Initialize DB ---
@st.cache_resource
def setup_database():
    init_db()
    ensure_admin_exists()
    return True


setup_database()


# --- Auth ---
user = require_auth()
if user is None:
    st.stop()

# --- Sidebar ---
with st.sidebar:
    st.markdown(f"### 👤 {user['username']}")
    st.caption(f"Role: {user['role']}")
    st.divider()
    logout()

# --- Dashboard ---
st.markdown('<p class="main-title">LitReview AI</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="subtitle">Automated Literature Review — Multi-Agent Research Survey</p>',
    unsafe_allow_html=True,
)
st.markdown("")

# --- Stats ---
from src.db.session import get_session
from src.db.models import Review, Paper

with get_session() as session:
    total_reviews = session.query(Review).filter_by(user_id=user["id"]).count()
    completed_reviews = (
        session.query(Review)
        .filter_by(user_id=user["id"], status="done")
        .count()
    )
    total_papers = session.query(Paper).count()

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-number">{total_reviews}</div>
            <div class="stat-label">Total Reviews</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col2:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-number">{completed_reviews}</div>
            <div class="stat-label">Completed</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col3:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-number">{total_papers}</div>
            <div class="stat-label">Papers Indexed</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("")
st.markdown("---")

# --- Quick Actions ---
st.markdown("### 🚀 Quick Actions")
qa_col1, qa_col2 = st.columns(2)
with qa_col1:
    if st.button("🔍 Start New Review", use_container_width=True, type="primary"):
        st.switch_page("pages/1_🔍_New_Review.py")
with qa_col2:
    if st.button("📚 View My Reviews", use_container_width=True):
        st.switch_page("pages/2_📚_My_Reviews.py")

# --- Recent Activity ---
st.markdown("### 📋 Recent Reviews")
with get_session() as session:
    recent = (
        session.query(Review)
        .filter_by(user_id=user["id"])
        .order_by(Review.created_at.desc())
        .limit(5)
        .all()
    )
    if recent:
        for review in recent:
            status_icon = {
                "pending": "⏳",
                "searching": "🔍",
                "filtering": "📊",
                "ranking": "📈",
                "synthesizing": "✍️",
                "reviewing": "🔎",
                "done": "✅",
                "failed": "❌",
            }.get(review.status, "❓")

            with st.container():
                r_col1, r_col2, r_col3 = st.columns([4, 2, 1])
                with r_col1:
                    st.markdown(f"**{review.title}**")
                    st.caption(review.topic[:100])
                with r_col2:
                    st.markdown(f"{status_icon} {review.status.capitalize()}")
                with r_col3:
                    if review.quality_score:
                        st.metric("Score", f"{review.quality_score:.1f}")
                st.divider()
    else:
        st.info("No reviews yet. Start your first literature review! 🎉")
