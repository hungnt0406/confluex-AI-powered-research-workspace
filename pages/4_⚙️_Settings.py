"""
Settings — API key management and preferences.
"""

import streamlit as st
from src.auth.auth_manager import require_auth

st.set_page_config(page_title="Settings | LitReview AI", page_icon="⚙️", layout="wide")

user = require_auth()
if user is None:
    st.stop()

st.markdown("## ⚙️ Settings")

# --- API Keys ---
st.markdown("### 🔑 API Keys")
st.markdown(
    "Providing API keys is **optional** but improves rate limits and access. "
    "Keys are stored securely in your browser session (not sent to our servers)."
)

with st.form("api_keys_form"):
    openai_key = st.text_input(
        "OpenAI API Key",
        type="password",
        value=st.session_state.get("user_openai_key", ""),
        help="Required for LLM synthesis (Stage 4-5). Get one at platform.openai.com",
    )

    anthropic_key = st.text_input(
        "Anthropic API Key",
        type="password",
        value=st.session_state.get("user_anthropic_key", ""),
        help="Alternative LLM provider. Get one at console.anthropic.com",
    )

    semantic_scholar_key = st.text_input(
        "Semantic Scholar API Key",
        type="password",
        value=st.session_state.get("user_ss_key", ""),
        help="Optional. Increases rate limits from 100/5min to much higher. Request at semanticscholar.org/product/api",
    )

    pubmed_email = st.text_input(
        "PubMed Email",
        value=st.session_state.get("user_pubmed_email", ""),
        help="Required by NCBI policy when using PubMed API.",
    )

    pubmed_key = st.text_input(
        "PubMed API Key",
        type="password",
        value=st.session_state.get("user_pubmed_key", ""),
        help="Optional. Increases rate limit from 3 to 10 requests/second.",
    )

    if st.form_submit_button("💾 Save Keys", type="primary", use_container_width=True):
        st.session_state["user_openai_key"] = openai_key
        st.session_state["user_anthropic_key"] = anthropic_key
        st.session_state["user_ss_key"] = semantic_scholar_key
        st.session_state["user_pubmed_email"] = pubmed_email
        st.session_state["user_pubmed_key"] = pubmed_key
        st.success("API keys saved to your session.")

st.markdown("---")

# --- Pipeline Preferences ---
st.markdown("### 🔧 Pipeline Preferences")

with st.form("preferences_form"):
    col1, col2 = st.columns(2)
    with col1:
        default_model = st.selectbox(
            "Default LLM Model",
            ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4-20250514", "claude-haiku"],
            index=0,
            help="Model used for literature review synthesis.",
        )
        similarity_threshold = st.slider(
            "Similarity Threshold",
            min_value=0.1,
            max_value=0.9,
            value=0.3,
            step=0.05,
            help="Minimum cosine similarity to keep a paper. Lower = more papers, higher = stricter.",
        )
    with col2:
        quality_threshold = st.slider(
            "Quality Threshold",
            min_value=1.0,
            max_value=10.0,
            value=7.0,
            step=0.5,
            help="Minimum quality score to accept a review. Lower = accept more, higher = stricter.",
        )
        max_retries = st.number_input(
            "Max Quality Retries",
            min_value=0,
            max_value=5,
            value=2,
            help="How many times to retry if quality check fails.",
        )

    if st.form_submit_button("💾 Save Preferences", use_container_width=True):
        st.session_state["pref_model"] = default_model
        st.session_state["pref_similarity_threshold"] = similarity_threshold
        st.session_state["pref_quality_threshold"] = quality_threshold
        st.session_state["pref_max_retries"] = max_retries
        st.success("Preferences saved.")

st.markdown("---")

# --- Admin Section ---
if user["role"] == "admin":
    st.markdown("### 👑 Admin — User Management")
    st.warning("Admin features will be available in Phase 5.")

    # TODO: Phase 5 — CRUD users
    # - List all users
    # - Create new user
    # - Change user role
    # - Delete user
