from types import SimpleNamespace

from backend.services.framework_service import FrameworkService


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def outerjoin(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, query_results):
        self.query_results = iter(query_results)

    def query(self, *args):
        return FakeQuery(next(self.query_results))


def test_framework_catalog_is_nested_and_database_backed():
    domain = SimpleNamespace(
        id=1, slug="llm", name="Large Language Models", description="LLM tools"
    )
    category = SimpleNamespace(
        id=2,
        domain_id=1,
        slug="inference",
        name="Inference",
        description="Serving tools",
        guide_url=None,
        guide_label=None,
    )
    framework = SimpleNamespace(
        id=3,
        category_id=2,
        slug="vllm",
        name="vLLM",
        organization_name="vLLM Project",
        description="Fast serving",
        when_to_use="GPU serving",
        docs_url="https://docs.vllm.ai/",
    )
    repository = SimpleNamespace(url="https://github.com/vllm-project/vllm")
    paper = SimpleNamespace(arxiv_id="2309.06180")
    platform = SimpleNamespace(framework_id=3, platform="gpu")
    service = FrameworkService(
        FakeSession(
            [[domain], [category], [(framework, repository, paper)], [platform]]
        )
    )

    catalog = service.get_catalog()

    item = catalog.domains[0].categories[0].frameworks[0]
    assert item.slug == "vllm"
    assert item.github_url == repository.url
    assert item.introducing_paper_arxiv_id == paper.arxiv_id
    assert item.platforms == ["gpu"]
