"""
Paper Library — Browse and search indexed papers.
"""

import streamlit as st
from src.auth.auth_manager import require_auth

st.set_page_config(page_title="Paper Library | LitReview AI", page_icon="📄", layout="wide")

user = require_auth()
if user is None:
    st.stop()

st.markdown("## 📄 Paper Library")
st.markdown("Browse papers from past reviews and the local index.")

from src.db.session import get_session
from src.db.models import Paper

# --- Search ---
col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    search = st.text_input("🔍 Search papers", placeholder="Search by title, author, or DOI...")
with col2:
    source_filter = st.selectbox(
        "Source",
        ["All", "semantic_scholar", "arxiv", "pubmed", "local_index"],
    )
with col3:
    year_filter = st.number_input("Year ≥", min_value=1990, max_value=2026, value=2020)

st.markdown("---")

# --- Load Papers ---
with get_session() as session:
    query = session.query(Paper)

    if source_filter != "All":
        query = query.filter_by(source=source_filter)

    if year_filter:
        query = query.filter(Paper.year >= year_filter)

    if search:
        query = query.filter(
            (Paper.title.ilike(f"%{search}%"))
            | (Paper.doi.ilike(f"%{search}%"))
        )

    total_count = query.count()
    papers = query.order_by(Paper.citation_count.desc().nullslast()).limit(50).all()

st.caption(f"Showing {len(papers)} of {total_count} papers")

if not papers:
    st.info("No papers in the library yet. Papers will be added when you run your first review.")
else:
    for paper in papers:
        source_emoji = {
            "semantic_scholar": "🔵",
            "arxiv": "🟠",
            "pubmed": "🟢",
            "local_index": "📁",
        }.get(paper.source, "⚪")

        with st.container():
            title_col, meta_col = st.columns([5, 1])
            with title_col:
                st.markdown(f"**{paper.title}**")
                authors_str = ", ".join(paper.authors[:3]) if paper.authors else "Unknown"
                if paper.authors and len(paper.authors) > 3:
                    authors_str += f" +{len(paper.authors) - 3} more"
                st.caption(
                    f"{source_emoji} {paper.source} | {paper.year or '?'} | {authors_str}"
                )
            with meta_col:
                if paper.citation_count:
                    st.metric("Citations", paper.citation_count)

            if paper.abstract:
                with st.expander("Abstract"):
                    st.markdown(paper.abstract[:1000])

            if paper.pdf_url:
                st.link_button("📎 PDF", paper.pdf_url, use_container_width=False)

            st.divider()
