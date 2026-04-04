"""
New Review — Create a new automated literature review.
"""

import streamlit as st
from src.auth.auth_manager import require_auth

st.set_page_config(page_title="New Review | LitReview AI", page_icon="🔍", layout="wide")

user = require_auth()
if user is None:
    st.stop()

st.markdown("## 🔍 New Literature Review")
st.markdown("Configure your research topic and constraints, then let the pipeline do the work.")

st.markdown("---")

# --- Topic Input ---
with st.form("new_review_form", clear_on_submit=False):
    title = st.text_input(
        "Review Title",
        placeholder="e.g., Applications of LLMs in Healthcare",
        help="A short title for your literature review.",
    )

    topic = st.text_area(
        "Research Topic",
        height=120,
        placeholder="Describe the research topic you want to survey...\ne.g., How are large language models being applied in clinical decision support, medical diagnosis, and drug discovery?",
        help="Be specific. The more detail you provide, the better the results.",
    )

    st.markdown("### Constraints")
    c1, c2, c3 = st.columns(3)
    with c1:
        year_min = st.number_input("Year From", min_value=1990, max_value=2026, value=2020)
    with c2:
        year_max = st.number_input("Year To", min_value=1990, max_value=2026, value=2026)
    with c3:
        max_papers = st.slider("Max Papers", min_value=5, max_value=50, value=20)

    categories = st.multiselect(
        "arXiv Categories (optional)",
        options=[
            "cs.AI", "cs.CL", "cs.CV", "cs.LG", "cs.IR", "cs.NE",
            "cs.RO", "cs.SE", "stat.ML", "q-bio", "physics",
        ],
        default=["cs.AI", "cs.CL"],
        help="Filter papers by arXiv category. Leave empty for broader search.",
    )

    keywords = st.text_input(
        "Additional Keywords (optional)",
        placeholder="e.g., transformer, attention, fine-tuning",
        help="Comma-separated keywords to boost search relevance.",
    )

    st.markdown("### Output Format")
    output_formats = st.multiselect(
        "Select output formats",
        options=["docx", "tex", "pdf"],
        default=["docx", "pdf"],
    )

    submitted = st.form_submit_button("🚀 Start Review", type="primary", use_container_width=True)

if submitted:
    if not title or not topic:
        st.error("Please provide both a title and a research topic.")
    else:
        # Build constraints dict
        constraints = {
            "year_min": year_min,
            "year_max": year_max,
            "max_papers": max_papers,
            "categories": categories,
            "keywords": [k.strip() for k in keywords.split(",") if k.strip()] if keywords else [],
            "output_formats": output_formats,
        }

        # Save to DB
        from src.db.session import get_session
        from src.db.models import Review

        with get_session() as session:
            review = Review(
                user_id=user["id"],
                title=title,
                topic=topic,
                constraints=constraints,
                status="pending",
            )
            session.add(review)
            session.commit()
            review_id = review.id

        st.success(f"Review **{title}** created! (ID: {review_id})")

        # TODO: Phase 3 — trigger pipeline execution here
        st.info("⏳ Pipeline execution will be available after Phase 3 implementation.")
        st.balloons()
