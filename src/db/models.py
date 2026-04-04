"""
SQLAlchemy models for the literature review application.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    LargeBinary,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # "admin" | "user"
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    reviews = relationship("Review", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    topic = Column(Text, nullable=False)
    constraints = Column(JSONB, nullable=True)  # {year_min, year_max, categories, max_papers, keywords}
    status = Column(
        String(50),
        nullable=False,
        default="pending",
    )  # pending | searching | filtering | ranking | synthesizing | reviewing | done | failed
    result_text = Column(Text, nullable=True)
    paper_count = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="reviews")
    review_papers = relationship(
        "ReviewPaper", back_populates="review", cascade="all, delete-orphan"
    )
    outputs = relationship(
        "ReviewOutput", back_populates="review", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Review(id={self.id}, topic='{self.topic[:50]}...', status='{self.status}')>"


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True)
    doi = Column(String(255), unique=True, nullable=True, index=True)
    arxiv_id = Column(String(50), nullable=True, index=True)
    title = Column(String(1000), nullable=False)
    authors = Column(JSONB, nullable=True)  # ["Author A", "Author B"]
    source = Column(
        String(50), nullable=False
    )  # semantic_scholar | arxiv | pubmed | local_index
    year = Column(Integer, nullable=True, index=True)
    abstract = Column(Text, nullable=True)
    pdf_url = Column(String(1000), nullable=True)
    citation_count = Column(Integer, nullable=True, default=0)
    categories = Column(JSONB, nullable=True)  # ["cs.AI", "cs.CL"]
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    review_papers = relationship("ReviewPaper", back_populates="paper")

    def __repr__(self):
        return f"<Paper(id={self.id}, title='{self.title[:50]}...', source='{self.source}')>"


class ReviewPaper(Base):
    __tablename__ = "review_papers"

    id = Column(Integer, primary_key=True)
    review_id = Column(
        Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    paper_id = Column(
        Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    relevance_score = Column(Float, nullable=True)  # cosine similarity
    composite_score = Column(Float, nullable=True)  # weighted final score
    summary = Column(Text, nullable=True)  # generated during synthesis
    status = Column(
        String(50), nullable=False, default="candidate"
    )  # candidate | filtered | ranked | cited

    __table_args__ = (
        UniqueConstraint("review_id", "paper_id", name="uq_review_paper"),
    )

    review = relationship("Review", back_populates="review_papers")
    paper = relationship("Paper", back_populates="review_papers")

    def __repr__(self):
        return f"<ReviewPaper(review={self.review_id}, paper={self.paper_id}, score={self.composite_score})>"


class ReviewOutput(Base):
    __tablename__ = "review_outputs"

    id = Column(Integer, primary_key=True)
    review_id = Column(
        Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    format = Column(String(10), nullable=False)  # docx | tex | pdf
    file_data = Column(LargeBinary, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    generated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    review = relationship("Review", back_populates="outputs")

    def __repr__(self):
        return f"<ReviewOutput(review={self.review_id}, format='{self.format}', v{self.version})>"
