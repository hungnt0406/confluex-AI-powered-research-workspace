"""
My Reviews — View and manage past literature reviews.
"""

import streamlit as st
from src.auth.auth_manager import require_auth

st.set_page_config(page_title="My Reviews | LitReview AI", page_icon="📚", layout="wide")

user = require_auth()
if user is None:
    st.stop()

st.markdown("## 📚 My Reviews")

from src.db.session import get_session
from src.db.models import Review, ReviewOutput

# --- Filters ---
col_f1, col_f2 = st.columns([3, 1])
with col_f1:
    search_query = st.text_input("🔍 Search reviews", placeholder="Search by title or topic...")
with col_f2:
    status_filter = st.selectbox(
        "Status",
        ["All", "pending", "searching", "filtering", "ranking", "synthesizing", "reviewing", "done", "failed"],
    )

st.markdown("---")

# --- Load Reviews ---
with get_session() as session:
    query = session.query(Review).filter_by(user_id=user["id"])

    if status_filter != "All":
        query = query.filter_by(status=status_filter)

    if search_query:
        query = query.filter(
            (Review.title.ilike(f"%{search_query}%"))
            | (Review.topic.ilike(f"%{search_query}%"))
        )

    reviews = query.order_by(Review.created_at.desc()).all()

    if not reviews:
        st.info("No reviews found. Create your first one from the **New Review** page!")
    else:
        for review in reviews:
            status_icon = {
                "pending": "⏳", "searching": "🔍", "filtering": "📊",
                "ranking": "📈", "synthesizing": "✍️", "reviewing": "🔎",
                "done": "✅", "failed": "❌",
            }.get(review.status, "❓")

            with st.expander(
                f"{status_icon} **{review.title}** — {review.created_at.strftime('%Y-%m-%d %H:%M')}",
                expanded=False,
            ):
                st.markdown(f"**Topic:** {review.topic}")
                st.markdown(f"**Status:** {review.status.capitalize()}")

                if review.constraints:
                    c = review.constraints
                    st.markdown(
                        f"**Constraints:** Years {c.get('year_min', '?')}–{c.get('year_max', '?')} | "
                        f"Max {c.get('max_papers', '?')} papers | "
                        f"Categories: {', '.join(c.get('categories', []))}"
                    )

                if review.paper_count:
                    st.markdown(f"**Papers Found:** {review.paper_count}")

                if review.quality_score:
                    st.metric("Quality Score", f"{review.quality_score:.1f}/10.0")

                if review.error_message:
                    st.error(f"Error: {review.error_message}")

                # --- Download outputs ---
                if review.status == "done":
                    outputs = (
                        session.query(ReviewOutput)
                        .filter_by(review_id=review.id)
                        .order_by(ReviewOutput.generated_at.desc())
                        .all()
                    )
                    if outputs:
                        st.markdown("**📥 Downloads:**")
                        dl_cols = st.columns(len(outputs))
                        for i, output in enumerate(outputs):
                            ext_map = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                       "tex": "text/x-tex", "pdf": "application/pdf"}
                            with dl_cols[i]:
                                st.download_button(
                                    f"⬇️ {output.format.upper()} (v{output.version})",
                                    data=output.file_data,
                                    file_name=f"{review.title.replace(' ', '_')}_v{output.version}.{output.format}",
                                    mime=ext_map.get(output.format, "application/octet-stream"),
                                    use_container_width=True,
                                )

                # --- Preview result ---
                if review.result_text:
                    with st.container():
                        st.markdown("**Preview:**")
                        st.markdown(review.result_text[:2000] + ("..." if len(review.result_text) > 2000 else ""))
