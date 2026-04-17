from __future__ import annotations

import re
from dataclasses import dataclass

from backend.db.models import Paper

LATEX_SPECIAL_CHARACTERS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class CitationArtifactBundle:
    """Deterministic citation artifacts keyed by selected paper id."""

    papers_by_id: dict[str, Paper]
    citation_keys_by_paper_id: dict[str, str]
    references_by_paper_id: dict[str, str]
    bibtex_entries_by_paper_id: dict[str, str]


class CitationFormatter:
    """Render inline citations and reference artifacts from persisted paper metadata."""

    def prepare_bundle(
        self,
        *,
        papers: list[Paper],
        reference_style: str,
    ) -> CitationArtifactBundle:
        citation_keys_by_paper_id = self._build_citation_keys(papers)
        papers_by_id = {paper.id: paper for paper in papers}

        return CitationArtifactBundle(
            papers_by_id=papers_by_id,
            citation_keys_by_paper_id=citation_keys_by_paper_id,
            references_by_paper_id={
                paper.id: self._format_reference_entry(paper, reference_style=reference_style)
                for paper in papers
            },
            bibtex_entries_by_paper_id={
                paper.id: self._build_bibtex_entry(
                    paper,
                    citation_key=citation_keys_by_paper_id[paper.id],
                )
                for paper in papers
            },
        )

    def format_inline_citation(
        self,
        *,
        paper_ids: list[str],
        citation_mode: str,
        bundle: CitationArtifactBundle,
    ) -> str:
        ordered_paper_ids = [
            paper_id for paper_id in bundle.papers_by_id if paper_id in set(paper_ids)
        ]
        if not ordered_paper_ids:
            return ""

        if citation_mode in {"latex_cite", "thebibliography"}:
            citation_keys = [
                bundle.citation_keys_by_paper_id[paper_id] for paper_id in ordered_paper_ids
            ]
            return rf"\cite{{{','.join(citation_keys)}}}"

        if citation_mode == "author_year":
            rendered_entries = [
                self._format_author_year_inline(bundle.papers_by_id[paper_id])
                for paper_id in ordered_paper_ids
            ]
            return f"({'; '.join(rendered_entries)})"

        numbered_entries = [
            str(index)
            for index, paper_id in enumerate(bundle.papers_by_id, start=1)
            if paper_id in set(ordered_paper_ids)
        ]
        return f"[{', '.join(numbered_entries)}]"

    def format_references(
        self,
        *,
        paper_ids: list[str],
        bundle: CitationArtifactBundle,
    ) -> list[str]:
        return [
            bundle.references_by_paper_id[paper_id]
            for paper_id in bundle.papers_by_id
            if paper_id in set(paper_ids)
        ]

    def format_bibtex_entries(
        self,
        *,
        paper_ids: list[str],
        bundle: CitationArtifactBundle,
    ) -> list[str]:
        return [
            bundle.bibtex_entries_by_paper_id[paper_id]
            for paper_id in bundle.papers_by_id
            if paper_id in set(paper_ids)
        ]

    def format_thebibliography(
        self,
        *,
        paper_ids: list[str],
        bundle: CitationArtifactBundle,
    ) -> str | None:
        ordered_paper_ids = [
            paper_id for paper_id in bundle.papers_by_id if paper_id in set(paper_ids)
        ]
        if not ordered_paper_ids:
            return None

        bibliography_items = [
            (
                rf"\bibitem{{{bundle.citation_keys_by_paper_id[paper_id]}}} "
                f"{self.escape_latex_text(bundle.references_by_paper_id[paper_id])}"
            )
            for paper_id in ordered_paper_ids
        ]
        return "\n".join(
            [
                r"\begin{thebibliography}{99}",
                *bibliography_items,
                r"\end{thebibliography}",
            ]
        )

    def escape_latex_text(self, text: str) -> str:
        """Escape plain text for safe LaTeX output."""

        return "".join(LATEX_SPECIAL_CHARACTERS.get(character, character) for character in text)

    def _build_citation_keys(self, papers: list[Paper]) -> dict[str, str]:
        citation_keys: dict[str, str] = {}
        seen_bases: dict[str, int] = {}

        for paper in papers:
            author_token = self._slugify(self._primary_author_surname(paper) or "paper")
            year_token = str(paper.year) if paper.year is not None else "nd"
            title_token = self._slugify(self._first_title_token(paper.title) or paper.id[:8])
            base_key = f"{author_token}{year_token}{title_token}"
            seen_count = seen_bases.get(base_key, 0)
            seen_bases[base_key] = seen_count + 1
            citation_keys[paper.id] = base_key if seen_count == 0 else f"{base_key}{seen_count + 1}"

        return citation_keys

    def _format_reference_entry(self, paper: Paper, *, reference_style: str) -> str:
        if reference_style == "apa":
            return self._format_apa_reference(paper)
        if reference_style == "chicago":
            return self._format_chicago_reference(paper)
        return self._format_ieee_reference(paper)

    def _format_ieee_reference(self, paper: Paper) -> str:
        segments: list[str] = []
        authors = self._format_ieee_authors(paper.authors)
        if authors:
            segments.append(authors)

        title = paper.title.strip()
        if title:
            segments.append(f'"{title}"')

        year = str(paper.year) if paper.year is not None else None
        if year:
            segments.append(year)

        identifier = paper.doi or paper.source_url or paper.pdf_url
        if identifier:
            segments.append(identifier)

        return ", ".join(segments) + "."

    def _format_apa_reference(self, paper: Paper) -> str:
        segments: list[str] = []
        authors = self._format_apa_authors(paper.authors)
        if authors:
            segments.append(authors)

        year = str(paper.year) if paper.year is not None else "n.d."
        segments.append(f"({year}).")
        segments.append(f"{paper.title.strip()}.")

        identifier = paper.doi or paper.source_url or paper.pdf_url
        if identifier:
            segments.append(identifier)

        return " ".join(segment for segment in segments if segment).strip()

    def _format_chicago_reference(self, paper: Paper) -> str:
        segments: list[str] = []
        authors = self._format_chicago_authors(paper.authors)
        if authors:
            segments.append(authors)

        title = paper.title.strip()
        if title:
            segments.append(f'"{title}."')

        if paper.year is not None:
            segments.append(str(paper.year))

        identifier = paper.doi or paper.source_url or paper.pdf_url
        if identifier:
            segments.append(identifier)

        return " ".join(segment for segment in segments if segment).strip()

    def _build_bibtex_entry(self, paper: Paper, *, citation_key: str) -> str:
        fields: list[str] = [
            f"  title = {{{paper.title.strip()}}}",
        ]

        authors = " and ".join(author.strip() for author in paper.authors if author.strip())
        if authors:
            fields.append(f"  author = {{{authors}}}")
        if paper.year is not None:
            fields.append(f"  year = {{{paper.year}}}")
        if paper.doi:
            fields.append(f"  doi = {{{paper.doi}}}")
        if paper.source_url:
            fields.append(f"  url = {{{paper.source_url}}}")
        elif paper.pdf_url:
            fields.append(f"  url = {{{paper.pdf_url}}}")

        return "\n".join(
            [
                f"@misc{{{citation_key},",
                *fields,
                "}",
            ]
        )

    def _format_author_year_inline(self, paper: Paper) -> str:
        surname = self._primary_author_surname(paper) or paper.title.strip()
        year = str(paper.year) if paper.year is not None else "n.d."
        return f"{surname}, {year}"

    def _format_ieee_authors(self, authors: list[str]) -> str:
        formatted_authors = [
            self._format_author_with_initials(author)
            for author in authors
            if author.strip()
        ]
        return self._join_authors(formatted_authors)

    def _format_apa_authors(self, authors: list[str]) -> str:
        formatted_authors = [
            self._format_author_as_surname_initials(author)
            for author in authors
            if author.strip()
        ]
        return self._join_authors(formatted_authors)

    def _format_chicago_authors(self, authors: list[str]) -> str:
        return self._join_authors([author.strip() for author in authors if author.strip()])

    def _format_author_with_initials(self, author: str) -> str:
        parts = [part for part in WHITESPACE_PATTERN.split(author.strip()) if part]
        if not parts:
            return author.strip()

        surname = parts[-1]
        initials = " ".join(f"{part[0]}." for part in parts[:-1] if part)
        return f"{initials} {surname}".strip()

    def _format_author_as_surname_initials(self, author: str) -> str:
        parts = [part for part in WHITESPACE_PATTERN.split(author.strip()) if part]
        if not parts:
            return author.strip()

        surname = parts[-1]
        initials = " ".join(f"{part[0]}." for part in parts[:-1] if part)
        return f"{surname}, {initials}".strip().rstrip(",")

    def _join_authors(self, authors: list[str]) -> str:
        if not authors:
            return ""
        if len(authors) == 1:
            return authors[0]
        if len(authors) == 2:
            return f"{authors[0]} and {authors[1]}"
        return ", ".join(authors[:-1]) + f", and {authors[-1]}"

    def _primary_author_surname(self, paper: Paper) -> str | None:
        if not paper.authors:
            return None
        first_author = paper.authors[0].strip()
        if not first_author:
            return None
        return first_author.split()[-1]

    def _first_title_token(self, title: str) -> str | None:
        title_tokens = [
            token
            for token in NON_ALPHANUMERIC_PATTERN.sub(" ", title.lower()).split()
            if len(token) > 2
        ]
        if not title_tokens:
            return None
        return title_tokens[0]

    def _slugify(self, value: str) -> str:
        normalized = NON_ALPHANUMERIC_PATTERN.sub("", value.lower())
        return normalized or "paper"
