"""Make writer documents user-owned and add document source links."""

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260513_01"
down_revision: str | None = "20260509_02"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "writer_documents",
        sa.Column("user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "reference_files",
        sa.Column("user_id", sa.String(length=36), nullable=True),
    )

    op.execute(
        """
        UPDATE writer_documents
        SET user_id = projects.user_id
        FROM projects
        WHERE writer_documents.project_id = projects.id
        """
    )
    op.execute(
        """
        UPDATE papers
        SET user_id = projects.user_id
        FROM projects
        WHERE papers.project_id = projects.id
        """
    )
    op.execute(
        """
        UPDATE reference_files
        SET user_id = projects.user_id
        FROM projects
        WHERE reference_files.project_id = projects.id
        """
    )

    op.alter_column("writer_documents", "user_id", nullable=False)
    op.create_index(op.f("ix_writer_documents_user_id"), "writer_documents", ["user_id"])
    op.create_index(op.f("ix_papers_user_id"), "papers", ["user_id"])
    op.create_index(op.f("ix_reference_files_user_id"), "reference_files", ["user_id"])

    op.create_foreign_key(
        "fk_writer_documents_user_id_users",
        "writer_documents",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_papers_user_id_users",
        "papers",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_reference_files_user_id_users",
        "reference_files",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("writer_documents_project_id_fkey", "writer_documents", type_="foreignkey")
    op.alter_column("writer_documents", "project_id", nullable=True)
    op.create_foreign_key(
        "fk_writer_documents_project_id_projects",
        "writer_documents",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column("papers", "project_id", nullable=True)
    op.alter_column("reference_files", "project_id", nullable=True)

    op.create_table(
        "writer_document_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("writer_document_id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=True),
        sa.Column("source_origin", sa.String(length=64), server_default="manual", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["writer_document_id"], ["writer_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "writer_document_id",
            "paper_id",
            name="uq_writer_document_sources_document_paper",
        ),
    )
    op.create_index(
        op.f("ix_writer_document_sources_paper_id"),
        "writer_document_sources",
        ["paper_id"],
    )
    op.create_index(
        op.f("ix_writer_document_sources_writer_document_id"),
        "writer_document_sources",
        ["writer_document_id"],
    )
    op.create_index(
        "ix_writer_document_sources_document_order",
        "writer_document_sources",
        ["writer_document_id", "order_index"],
    )

    _backfill_writer_document_sources()


def downgrade() -> None:
    op.drop_index("ix_writer_document_sources_document_order", table_name="writer_document_sources")
    op.drop_index(op.f("ix_writer_document_sources_writer_document_id"), table_name="writer_document_sources")
    op.drop_index(op.f("ix_writer_document_sources_paper_id"), table_name="writer_document_sources")
    op.drop_table("writer_document_sources")

    op.drop_constraint("fk_writer_documents_project_id_projects", "writer_documents", type_="foreignkey")
    op.execute("DELETE FROM writer_documents WHERE project_id IS NULL")
    op.execute("DELETE FROM papers WHERE project_id IS NULL")
    op.execute("DELETE FROM reference_files WHERE project_id IS NULL")
    op.alter_column("writer_documents", "project_id", nullable=False)
    op.alter_column("papers", "project_id", nullable=False)
    op.alter_column("reference_files", "project_id", nullable=False)
    op.create_foreign_key(
        "writer_documents_project_id_fkey",
        "writer_documents",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("fk_reference_files_user_id_users", "reference_files", type_="foreignkey")
    op.drop_constraint("fk_papers_user_id_users", "papers", type_="foreignkey")
    op.drop_constraint("fk_writer_documents_user_id_users", "writer_documents", type_="foreignkey")
    op.drop_index(op.f("ix_reference_files_user_id"), table_name="reference_files")
    op.drop_index(op.f("ix_papers_user_id"), table_name="papers")
    op.drop_index(op.f("ix_writer_documents_user_id"), table_name="writer_documents")
    op.drop_column("reference_files", "user_id")
    op.drop_column("papers", "user_id")
    op.drop_column("writer_documents", "user_id")


def _backfill_writer_document_sources() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, source_paper_ids_json FROM writer_documents")
    ).mappings()
    for row in rows:
        raw_ids = row["source_paper_ids_json"] or []
        if isinstance(raw_ids, str):
            try:
                paper_ids = json.loads(raw_ids)
            except json.JSONDecodeError:
                paper_ids = []
        else:
            paper_ids = raw_ids

        for index, paper_id in enumerate(dict.fromkeys(paper_ids)):
            if not paper_id:
                continue
            connection.execute(
                sa.text(
                    """
                    INSERT INTO writer_document_sources (
                        id,
                        writer_document_id,
                        paper_id,
                        source_origin,
                        order_index
                    )
                    VALUES (
                        :id,
                        :writer_document_id,
                        :paper_id,
                        'legacy',
                        :order_index
                    )
                    """
                ),
                {
                    "id": str(uuid4()),
                    "writer_document_id": row["id"],
                    "paper_id": paper_id,
                    "order_index": index,
                },
            )
