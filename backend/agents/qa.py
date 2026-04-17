from __future__ import annotations

import re
from dataclasses import dataclass

from backend.db.models import Paper

AUTHOR_YEAR_CITATION_PATTERN = re.compile(r"\([^)]+,\s*(?:n\.d\.|\d{4})(?:;\s*[^)]+,\s*(?:n\.d\.|\d{4}))*\)")
LATEX_CITATION_PATTERN = re.compile(r"\\cite\{([^}]+)\}")
NUMBERED_CITATION_PATTERN = re.compile(r"\[(\d+(?:,\s*\d+)*)\]")
COMPARATIVE_LANGUAGE_PATTERN = re.compile(
    r"\b(compare|comparison|better|worse|outperform|outperforms|higher|lower|improves|improved)\b",
    re.IGNORECASE,
)
HEADING_PATTERN = re.compile(r"^(?:#+\s+|\\(?:sub)*section\{).+")
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class WriterQaFlag:
    """Machine-readable QA issue emitted for generated writer output."""

    issue: str
    severity: str
    location: str


class WriterQAAgent:
    """Rule-based QA validator for grounded writer outputs."""

    def validate_output(
        self,
        *,
        body: str,
        references: list[str],
        bibtex_entries: list[str],
        thebibliography: str | None,
        selected_papers: list[Paper],
        citation_mode: str,
        artifact_paper_ids: list[str],
        citation_keys_by_paper_id: dict[str, str],
    ) -> list[WriterQaFlag]:
        qa_flags: list[WriterQaFlag] = []

        if not body.strip() and not references and not bibtex_entries and not (thebibliography or "").strip():
            qa_flags.append(
                WriterQaFlag(
                    issue="Generated output is empty.",
                    severity="error",
                    location="output",
                )
            )

        qa_flags.extend(
            self._validate_body_citations(
                body=body,
                citation_mode=citation_mode,
                artifact_paper_ids=artifact_paper_ids,
                citation_keys_by_paper_id=citation_keys_by_paper_id,
            )
        )
        qa_flags.extend(
            self._validate_reference_metadata(
                selected_papers=selected_papers,
                artifact_paper_ids=artifact_paper_ids,
            )
        )

        if citation_mode == "thebibliography":
            normalized_thebibliography = (thebibliography or "").strip()
            if not normalized_thebibliography:
                qa_flags.append(
                    WriterQaFlag(
                        issue="LaTeX thebibliography output was requested but no thebibliography block was generated.",
                        severity="error",
                        location="thebibliography",
                    )
                )
            elif not normalized_thebibliography.startswith(r"\begin{thebibliography}") or not normalized_thebibliography.endswith(
                r"\end{thebibliography}"
            ):
                qa_flags.append(
                    WriterQaFlag(
                        issue="Generated thebibliography output is malformed.",
                        severity="error",
                        location="thebibliography",
                    )
                )

        if citation_mode == "bibtex_only" and not bibtex_entries:
            qa_flags.append(
                WriterQaFlag(
                    issue="BibTeX output was requested but no BibTeX entries were generated.",
                    severity="error",
                    location="bibtex_entries",
                )
            )

        if body.strip() and not self._body_mentions_selected_papers(
            body=body,
            selected_papers=selected_papers,
            citation_mode=citation_mode,
        ):
            qa_flags.append(
                WriterQaFlag(
                    issue="Generated prose is suspiciously generic and does not clearly reference the selected papers.",
                    severity="warning",
                    location="body",
                )
            )

        return qa_flags

    def _validate_body_citations(
        self,
        *,
        body: str,
        citation_mode: str,
        artifact_paper_ids: list[str],
        citation_keys_by_paper_id: dict[str, str],
    ) -> list[WriterQaFlag]:
        qa_flags: list[WriterQaFlag] = []
        normalized_body = body.strip()
        if not normalized_body or citation_mode == "bibtex_only":
            return qa_flags

        if citation_mode in {"latex_cite", "thebibliography"}:
            valid_keys = {
                citation_keys_by_paper_id[paper_id]
                for paper_id in artifact_paper_ids
                if paper_id in citation_keys_by_paper_id
            }
            for match in LATEX_CITATION_PATTERN.finditer(normalized_body):
                keys = [item.strip() for item in match.group(1).split(",") if item.strip()]
                for key in keys:
                    if key not in valid_keys:
                        qa_flags.append(
                            WriterQaFlag(
                                issue="Citation key appears in the body but no matching reference artifact was generated.",
                                severity="error",
                                location="body",
                            )
                        )
                        break

        elif citation_mode == "numbered":
            max_reference_index = len(artifact_paper_ids)
            for match in NUMBERED_CITATION_PATTERN.finditer(normalized_body):
                numbers = [item.strip() for item in match.group(1).split(",") if item.strip()]
                for number in numbers:
                    if not number.isdigit() or int(number) < 1 or int(number) > max_reference_index:
                        qa_flags.append(
                            WriterQaFlag(
                                issue="Numbered citation appears in the body but no matching reference entry was generated.",
                                severity="error",
                                location="body",
                            )
                        )
                        break

        body_paragraphs = [
            paragraph.strip()
            for paragraph in normalized_body.split("\n\n")
            if paragraph.strip()
        ]
        for paragraph in body_paragraphs:
            if HEADING_PATTERN.match(paragraph):
                continue
            if not self._paragraph_has_citation(paragraph=paragraph, citation_mode=citation_mode):
                severity = "error" if COMPARATIVE_LANGUAGE_PATTERN.search(paragraph) else "warning"
                issue = (
                    "Comparative claim appears without an attached citation."
                    if severity == "error"
                    else "Paragraph appears unsupported because it does not contain a citation marker."
                )
                qa_flags.append(WriterQaFlag(issue=issue, severity=severity, location="body"))

        return qa_flags

    def _validate_reference_metadata(
        self,
        *,
        selected_papers: list[Paper],
        artifact_paper_ids: list[str],
    ) -> list[WriterQaFlag]:
        qa_flags: list[WriterQaFlag] = []
        artifact_paper_id_set = set(artifact_paper_ids)

        for paper in selected_papers:
            if paper.id not in artifact_paper_id_set:
                continue
            if not paper.authors:
                qa_flags.append(
                    WriterQaFlag(
                        issue=f"Reference entry for paper '{paper.title}' is missing author metadata.",
                        severity="warning",
                        location="references",
                    )
                )
            if paper.year is None:
                qa_flags.append(
                    WriterQaFlag(
                        issue=f"Reference entry for paper '{paper.title}' is missing year metadata.",
                        severity="warning",
                        location="references",
                    )
                )

        return qa_flags

    def _paragraph_has_citation(self, *, paragraph: str, citation_mode: str) -> bool:
        if citation_mode in {"latex_cite", "thebibliography"}:
            return LATEX_CITATION_PATTERN.search(paragraph) is not None
        if citation_mode == "author_year":
            return AUTHOR_YEAR_CITATION_PATTERN.search(paragraph) is not None
        return NUMBERED_CITATION_PATTERN.search(paragraph) is not None

    def _body_mentions_selected_papers(
        self,
        *,
        body: str,
        selected_papers: list[Paper],
        citation_mode: str,
    ) -> bool:
        if citation_mode in {"latex_cite", "thebibliography"} and LATEX_CITATION_PATTERN.search(body):
            return True
        if citation_mode == "numbered" and NUMBERED_CITATION_PATTERN.search(body):
            return True
        if citation_mode == "author_year" and AUTHOR_YEAR_CITATION_PATTERN.search(body):
            return True

        normalized_body = WHITESPACE_PATTERN.sub(" ", body.lower())
        for paper in selected_papers:
            title = paper.title.lower()
            surname = paper.authors[0].split()[-1].lower() if paper.authors else ""
            if title and title in normalized_body:
                return True
            if surname and surname in normalized_body:
                return True
        return False
