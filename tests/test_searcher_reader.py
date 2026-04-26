from sqlalchemy import select

from backend.agents.reader import ReaderAgent
from backend.agents.searcher import ReferencePaperContext, SearcherAgent
from backend.agents.state import AgentState
from backend.db.models import Paper, Project, ReferenceFile, Summary
from backend.services.llm import StructuredOutputError
from backend.services.reference_files import REFERENCE_SOURCE


class FakeQueryPlanner:
    def __init__(self, payload):
        self.payload = payload

    def is_configured(self) -> bool:
        return True

    async def generate_json(self, *, system_prompt, user_prompt, schema, max_tokens=1024, feature=None):
        return self.payload


class CapturingQueryPlanner(FakeQueryPlanner):
    def __init__(self, payload):
        super().__init__(payload)
        self.user_prompt = ""

    async def generate_json(self, *, system_prompt, user_prompt, schema, max_tokens=1024, feature=None):
        self.user_prompt = user_prompt
        return self.payload


class FakeSearchClient:
    def __init__(self, results_by_query):
        self.results_by_query = results_by_query

    async def search_papers(self, query, year_start, limit):
        return self.results_by_query.get(query, [])[:limit]


class FakeEmbeddingService:
    def __init__(self, embeddings):
        self.embeddings = embeddings

    async def embed_texts(self, texts, *, feature=None):
        return self.embeddings

    def embed_texts_locally(self, texts):
        return self.embeddings


class FakeSummaryGenerator:
    def __init__(self):
        self.calls = {}

    def is_configured(self) -> bool:
        return True

    async def generate_json(self, *, system_prompt, user_prompt, schema, max_tokens=1024, feature=None):
        if "Reliable Paper" in user_prompt:
            return {
                "problem": "Improve paper ranking",
                "method": "Use a relevance scoring pipeline",
                "result": "The system improved ranking quality",
                "relevance": "It directly supports the literature review topic.",
            }

        call_count = self.calls.get(user_prompt, 0)
        self.calls[user_prompt] = call_count + 1
        raise StructuredOutputError("mock summary failure")


async def test_searcher_agent_deduplicates_filters_and_persists_candidates(
    session_factory,
    sample_project,
) -> None:
    query_payload = {
        "queries": [
            {"query": "multi agent systems", "focus": "broad"},
            {"query": "multi agent systems survey", "focus": "survey"},
            {"query": "multi agent systems ranking", "focus": "ranking"},
            {"query": "multi agent systems benchmarks", "focus": "benchmark"},
            {"query": "multi agent systems recent advances", "focus": "recent"},
        ]
    }
    good_abstract = "This abstract is long enough to pass the quality filter. " * 4
    search_results = {
        "multi agent systems": [
            {
                "title": "Reliable Multi-Agent Review",
                "authors": ["Jane Doe"],
                "year": 2024,
                "abstract": good_abstract,
                "doi": "10.1000/reliable",
                "source": "semantic_scholar",
                "source_paper_id": "semantic-001",
                "source_url": "https://www.semanticscholar.org/paper/semantic-001",
                "pdf_url": "https://pdf.example.com/semantic-001.pdf",
                "citation_count": 124,
                "reference_count": 37,
                "relevance_score": None,
            },
            {
                "title": "Reliable Multi-Agent Review",
                "authors": ["Jane Doe"],
                "year": 2024,
                "abstract": good_abstract,
                "doi": None,
                "source": "arxiv",
                "source_paper_id": "2401.12345v1",
                "source_url": "http://arxiv.org/abs/2401.12345v1",
                "pdf_url": "http://arxiv.org/pdf/2401.12345v1",
                "relevance_score": None,
            },
            {
                "title": "Outdated Paper",
                "authors": ["John Doe"],
                "year": 2010,
                "abstract": good_abstract,
                "doi": "10.1000/old",
                "source": "semantic_scholar",
                "source_paper_id": "semantic-002",
                "source_url": "https://www.semanticscholar.org/paper/semantic-002",
                "pdf_url": "https://pdf.example.com/semantic-002.pdf",
                "relevance_score": None,
            },
            {
                "title": "Short Abstract Paper",
                "authors": ["John Doe"],
                "year": 2024,
                "abstract": "too short",
                "doi": "10.1000/short",
                "source": "semantic_scholar",
                "source_paper_id": "semantic-003",
                "source_url": "https://www.semanticscholar.org/paper/semantic-003",
                "pdf_url": "https://pdf.example.com/semantic-003.pdf",
                "relevance_score": None,
            },
        ],
        "multi agent systems ranking": [
            {
                "title": "Ranking Agentic Workflows",
                "authors": ["Alex Roe"],
                "year": 2023,
                "abstract": good_abstract,
                "doi": "10.1000/ranking",
                "source": "semantic_scholar",
                "source_paper_id": "semantic-004",
                "source_url": "https://www.semanticscholar.org/paper/semantic-004",
                "pdf_url": "https://pdf.example.com/semantic-004.pdf",
                "citation_count": 18,
                "reference_count": 9,
                "relevance_score": None,
            }
        ],
    }

    searcher = SearcherAgent(
        llm_service=FakeQueryPlanner(query_payload),
        search_clients=[FakeSearchClient(search_results)],
        minimum_abstract_length=100,
        per_query_limit=10,
    )

    async with session_factory() as session:
        project = (
            await session.execute(select(Project).where(Project.id == sample_project["id"]))
        ).scalar_one()
        result = await searcher.run(
            AgentState(project_id=project.id, topic=project.topic_description),
            session,
            project,
        )
        persisted_papers = (
            await session.execute(select(Paper).where(Paper.project_id == project.id))
        ).scalars().all()

    assert result["queries"][0] == "multi agent systems"
    assert len(result["raw_papers"]) == 2
    assert len(persisted_papers) == 2
    assert {paper.title for paper in persisted_papers} == {
        "Reliable Multi-Agent Review",
        "Ranking Agentic Workflows",
    }
    assert all(paper.status == "candidate" for paper in persisted_papers)
    persisted_papers_by_title = {paper.title: paper for paper in persisted_papers}
    assert persisted_papers_by_title["Reliable Multi-Agent Review"].source_paper_id == "semantic-001"
    assert (
        persisted_papers_by_title["Reliable Multi-Agent Review"].source_url
        == "https://www.semanticscholar.org/paper/semantic-001"
    )
    assert (
        persisted_papers_by_title["Reliable Multi-Agent Review"].pdf_url
        == "https://pdf.example.com/semantic-001.pdf"
    )
    assert persisted_papers_by_title["Reliable Multi-Agent Review"].citation_count == 124
    assert persisted_papers_by_title["Reliable Multi-Agent Review"].reference_count == 37
    assert persisted_papers_by_title["Ranking Agentic Workflows"].source_paper_id == "semantic-004"
    assert persisted_papers_by_title["Ranking Agentic Workflows"].citation_count == 18
    assert persisted_papers_by_title["Ranking Agentic Workflows"].reference_count == 9


async def test_searcher_agent_backfills_missing_provider_metadata_with_none(
    session_factory,
    sample_project,
) -> None:
    query_payload = {
        "queries": [
            {"query": "paper understanding", "focus": "broad"},
            {"query": "paper understanding survey", "focus": "survey"},
            {"query": "paper understanding ranking", "focus": "ranking"},
            {"query": "paper understanding recent advances", "focus": "recent"},
            {"query": "paper understanding benchmarks", "focus": "benchmark"},
        ]
    }
    good_abstract = "This abstract is long enough to pass the quality filter. " * 4
    search_results = {
        "paper understanding": [
            {
                "title": "Legacy Candidate Payload",
                "authors": ["Jane Doe"],
                "year": 2024,
                "abstract": good_abstract,
                "doi": "10.1000/legacy",
                "source": "semantic_scholar",
                "relevance_score": None,
            }
        ]
    }

    searcher = SearcherAgent(
        llm_service=FakeQueryPlanner(query_payload),
        search_clients=[FakeSearchClient(search_results)],
        minimum_abstract_length=100,
        per_query_limit=10,
    )

    async with session_factory() as session:
        project = (
            await session.execute(select(Project).where(Project.id == sample_project["id"]))
        ).scalar_one()
        await searcher.run(
            AgentState(project_id=project.id, topic=project.topic_description),
            session,
            project,
        )
        persisted_paper = (
            await session.execute(select(Paper).where(Paper.project_id == project.id))
        ).scalar_one()

    assert persisted_paper.title == "Legacy Candidate Payload"
    assert persisted_paper.source_paper_id is None
    assert persisted_paper.source_url is None
    assert persisted_paper.pdf_url is None
    assert persisted_paper.citation_count is None
    assert persisted_paper.reference_count is None


async def test_searcher_named_entity_topic_uses_conservative_queries() -> None:
    searcher = SearcherAgent(
        llm_service=FakeQueryPlanner(
            {
                "queries": [
                    {"query": '"TrackNet" AND "autonomous driving"', "focus": "hallucinated"},
                ]
            }
        ),
        search_clients=[],
    )

    queries, errors = await searcher.expand_queries("TrackNet")

    assert errors == []
    assert [query.query for query in queries] == [
        "TrackNet",
        "TrackNet paper",
        "TrackNet model",
        "TrackNet architecture",
        "TrackNet benchmark",
        "TrackNet survey",
    ]


async def test_searcher_sanitizes_boolean_queries_and_salvages_short_batches() -> None:
    searcher = SearcherAgent(
        llm_service=FakeQueryPlanner(
            {
                "queries": [
                    {
                        "query": '"vision transformer" AND "medical image segmentation" AND ("3D imaging" OR "volumetric data")',
                        "focus": "recent work angle " * 30,
                    },
                    {
                        "query": '"vision transformer" AND "medical image segmentation"',
                        "focus": "broad overview",
                    },
                ]
            }
        ),
        search_clients=[],
    )

    queries, errors = await searcher.expand_queries("vision transformer medical image segmentation")

    assert errors == []
    assert queries[0].query == "vision transformer medical image segmentation 3D imaging volumetric data"
    assert len(queries[0].focus) <= 255
    assert len(queries) >= 5


async def test_searcher_query_expansion_receives_uploaded_reference_context() -> None:
    planner = CapturingQueryPlanner(
        {
            "queries": [
                {"query": "literature review retrieval", "focus": "broad"},
                {"query": "uploaded seed reference retrieval", "focus": "seed"},
                {"query": "citation aware literature review", "focus": "citation"},
                {"query": "academic paper recommendation", "focus": "recommendation"},
                {"query": "multi source paper search", "focus": "search"},
            ]
        }
    )
    searcher = SearcherAgent(llm_service=planner, search_clients=[])

    queries, errors = await searcher.expand_queries(
        "literature review retrieval",
        reference_context=[
            ReferencePaperContext(
                title="Uploaded Seed Paper",
                year=2024,
                abstract="This uploaded paper studies retrieval for literature review agents.",
                doi=None,
            )
        ],
    )

    assert errors == []
    assert queries[0].query == "literature review retrieval"
    assert "The user has already uploaded these seed reference papers" in planner.user_prompt
    assert "Uploaded Seed Paper (2024)" in planner.user_prompt


async def test_searcher_preserves_uploaded_reference_papers_and_deduplicates_against_them(
    session_factory,
    sample_project,
) -> None:
    query_payload = {
        "queries": [
            {"query": "reference aware retrieval", "focus": "broad"},
            {"query": "reference aware retrieval survey", "focus": "survey"},
            {"query": "reference aware retrieval benchmark", "focus": "benchmark"},
            {"query": "reference aware retrieval citations", "focus": "citations"},
            {"query": "reference aware retrieval agents", "focus": "agents"},
        ]
    }
    good_abstract = "This abstract is long enough to pass the quality filter. " * 4
    search_results = {
        "reference aware retrieval": [
            {
                "title": "Uploaded Reference Paper",
                "authors": ["Jane Doe"],
                "year": 2024,
                "abstract": good_abstract,
                "doi": "10.1000/uploaded",
                "source": "semantic_scholar",
                "source_paper_id": "duplicate-doi",
                "source_url": "https://example.test/duplicate-doi",
                "pdf_url": None,
                "relevance_score": None,
            },
            {
                "title": "Uploaded Reference Paper",
                "authors": ["Jane Doe"],
                "year": 2024,
                "abstract": good_abstract,
                "doi": None,
                "source": "arxiv",
                "source_paper_id": "duplicate-title",
                "source_url": "https://example.test/duplicate-title",
                "pdf_url": None,
                "relevance_score": None,
            },
            {
                "title": "New External Paper",
                "authors": ["Alex Roe"],
                "year": 2023,
                "abstract": good_abstract,
                "doi": "10.1000/external",
                "source": "semantic_scholar",
                "source_paper_id": "external",
                "source_url": "https://example.test/external",
                "pdf_url": None,
                "relevance_score": None,
            },
        ]
    }
    searcher = SearcherAgent(
        llm_service=FakeQueryPlanner(query_payload),
        search_clients=[FakeSearchClient(search_results)],
        minimum_abstract_length=100,
        per_query_limit=10,
    )

    async with session_factory() as session:
        project = (
            await session.execute(select(Project).where(Project.id == sample_project["id"]))
        ).scalar_one()
        reference_file = ReferenceFile(
            project_id=project.id,
            original_filename="uploaded.pdf",
            content_type="application/pdf",
            byte_size=100,
            sha256="abc123",
            storage_path="/tmp/uploaded.pdf",
            parse_status="parsed",
            extracted_title="Uploaded Reference Paper",
            extracted_authors=["Jane Doe"],
            extracted_year=2024,
            extracted_abstract=good_abstract,
            extracted_text=good_abstract,
        )
        session.add(reference_file)
        await session.flush()

        uploaded_paper = Paper(
            project_id=project.id,
            reference_file_id=reference_file.id,
            title="Uploaded Reference Paper",
            authors=["Jane Doe"],
            year=2024,
            abstract=good_abstract,
            doi="10.1000/uploaded",
            source=REFERENCE_SOURCE,
            status="summarized",
            relevance_score=75.0,
        )
        old_external_paper = Paper(
            project_id=project.id,
            title="Old External Paper",
            authors=["John Doe"],
            year=2022,
            abstract=good_abstract,
            doi="10.1000/old",
            source="semantic_scholar",
            status="summarized",
            relevance_score=50.0,
        )
        session.add_all([uploaded_paper, old_external_paper])
        await session.flush()
        session.add(
            Summary(
                paper_id=uploaded_paper.id,
                problem="Old problem",
                method="Old method",
                result="Old result",
                relevance_to_topic="Old relevance",
                has_error=False,
            )
        )
        await session.commit()

        result = await searcher.run(
            AgentState(project_id=project.id, topic=project.topic_description),
            session,
            project,
        )
        persisted_papers = (
            await session.execute(select(Paper).where(Paper.project_id == project.id))
        ).scalars().all()
        persisted_summaries = (
            await session.execute(select(Summary).join(Paper).where(Paper.project_id == project.id))
        ).scalars().all()

    assert [paper["title"] for paper in result["raw_papers"]] == [
        "Uploaded Reference Paper",
        "New External Paper",
    ]
    assert {paper.title for paper in persisted_papers} == {
        "Uploaded Reference Paper",
        "New External Paper",
    }
    assert {paper.source for paper in persisted_papers} == {REFERENCE_SOURCE, "semantic_scholar"}
    assert all(paper.status == "candidate" for paper in persisted_papers)
    assert all(paper.relevance_score is None for paper in persisted_papers)
    assert persisted_summaries == []


async def test_searcher_prefers_more_groundable_pdf_url_for_duplicates(
    session_factory,
    sample_project,
) -> None:
    query_payload = {
        "queries": [
            {"query": "groundable duplicate resolution", "focus": "broad"},
            {"query": "groundable duplicate resolution survey", "focus": "survey"},
            {"query": "groundable duplicate resolution benchmark", "focus": "benchmark"},
            {"query": "groundable duplicate resolution citations", "focus": "citations"},
            {"query": "groundable duplicate resolution agents", "focus": "agents"},
        ]
    }
    good_abstract = "This abstract is long enough to pass the quality filter. " * 4
    search_results = {
        "groundable duplicate resolution": [
            {
                "title": "Groundable Duplicate Paper",
                "authors": ["Jane Doe"],
                "year": 2024,
                "abstract": good_abstract,
                "doi": "10.1000/groundable-duplicate",
                "source": "semantic_scholar",
                "source_paper_id": "semantic-blocked",
                "source_url": "https://www.semanticscholar.org/paper/semantic-blocked",
                "pdf_url": "https://content.example.com/download/paper?id=123",
                "relevance_score": None,
            },
            {
                "title": "Groundable Duplicate Paper",
                "authors": ["Jane Doe"],
                "year": 2024,
                "abstract": good_abstract,
                "doi": None,
                "source": "arxiv",
                "source_paper_id": "2401.99999v1",
                "source_url": "https://arxiv.org/abs/2401.99999v1",
                "pdf_url": "https://arxiv.org/pdf/2401.99999v1.pdf",
                "relevance_score": None,
            },
        ]
    }
    searcher = SearcherAgent(
        llm_service=FakeQueryPlanner(query_payload),
        search_clients=[FakeSearchClient(search_results)],
        minimum_abstract_length=100,
        per_query_limit=10,
    )

    async with session_factory() as session:
        project = (
            await session.execute(select(Project).where(Project.id == sample_project["id"]))
        ).scalar_one()
        await searcher.run(
            AgentState(project_id=project.id, topic=project.topic_description),
            session,
            project,
        )
        persisted_papers = (
            await session.execute(select(Paper).where(Paper.project_id == project.id))
        ).scalars().all()

    assert len(persisted_papers) == 1
    assert persisted_papers[0].title == "Groundable Duplicate Paper"
    assert persisted_papers[0].source == "arxiv"
    assert persisted_papers[0].source_paper_id == "2401.99999v1"
    assert persisted_papers[0].pdf_url == "https://arxiv.org/pdf/2401.99999v1.pdf"


async def test_reader_agent_ranks_papers_and_records_summary_failures(
    session_factory,
    sample_project,
) -> None:
    async with session_factory() as session:
        project = (
            await session.execute(select(Project).where(Project.id == sample_project["id"]))
        ).scalar_one()
        project.summary_limit = 2

        reliable_paper = Paper(
            project_id=project.id,
            title="Reliable Paper",
            authors=["Jane Doe"],
            year=2024,
            abstract="This paper introduces a reliable ranking pipeline for multi-agent retrieval." * 3,
            doi="10.1000/reliable",
            source="semantic_scholar",
            status="candidate",
            relevance_score=None,
        )
        unstable_paper = Paper(
            project_id=project.id,
            title="Unstable Paper",
            authors=["John Doe"],
            year=2024,
            abstract="This paper studies unstable summaries in retrieval pipelines." * 3,
            doi="10.1000/unstable",
            source="arxiv",
            status="candidate",
            relevance_score=None,
        )
        session.add_all([reliable_paper, unstable_paper])
        await session.commit()

        reader = ReaderAgent(
            embedding_service=FakeEmbeddingService(
                [
                    [1.0, 0.0],
                    [1.0, 0.0],
                    [0.1, 1.0],
                ]
            ),
            summary_generator=FakeSummaryGenerator(),
            summary_concurrency=2,
        )

        result = await reader.run(
            AgentState(project_id=project.id, topic=project.topic_description),
            session,
            project,
        )
        persisted_summaries = (
            await session.execute(select(Summary).join(Paper).where(Paper.project_id == project.id))
        ).scalars().all()
        persisted_papers = (
            await session.execute(select(Paper).where(Paper.project_id == project.id))
        ).scalars().all()

    assert len(result["ranked_papers"]) == 2
    assert len(result["summaries"]) == 2
    assert len(persisted_summaries) == 2
    assert any(summary.has_error for summary in persisted_summaries)
    assert any(not summary.has_error for summary in persisted_summaries)
    assert {paper.status for paper in persisted_papers} == {"summarized", "summary_error"}
