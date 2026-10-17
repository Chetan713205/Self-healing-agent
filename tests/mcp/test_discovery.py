"""The server discovers routes and imports from a FastAPI app it has never seen."""

from mcp_server.contracts import discover_probes
from mcp_server.tools.impact_tools import analyze_impact


def test_unfamiliar_fastapi_project_needs_no_endpoint_table(monkeypatch, tmp_path) -> None:
    package = tmp_path / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "catalog.py").write_text(
        "def get_product(product_id: int) -> dict:\n"
        "    return {'id': 7, 'name': 'pencil'}\n",
        encoding="utf-8",
    )
    (package / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from pydantic import BaseModel, Field\n"
        "from shop.catalog import get_product\n"
        "\n"
        "class Product(BaseModel):\n"
        "    id: int = Field(examples=[7])\n"
        "    name: str\n"
        "\n"
        "app = FastAPI()\n"
        "\n"
        "@app.get('/products/{product_id}', response_model=Product)\n"
        "def read_product(product_id: int) -> Product:\n"
        "    return Product(**get_product(product_id))\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_catalog.py").write_text(
        "from shop.catalog import get_product\n"
        "\n"
        "def test_get_product() -> None:\n"
        "    assert get_product(7)['name'] == 'pencil'\n",
        encoding="utf-8",
    )
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "product.json").write_text(
        """{
  "title": "Product",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "name"],
  "properties": {
    "id": {"type": "integer", "examples": [7]},
    "name": {"type": "string"}
  }
}
""",
        encoding="utf-8",
    )

    probes = discover_probes(tmp_path)
    assert probes["ok"] is True
    assert probes["skipped"] == []
    assert [probe["path"] for probe in probes["probes"]] == ["/products/7"]
    assert probes["probes"][0]["contract"] == "product.json"

    monkeypatch.setenv("GUARDIAN_REPO_ROOT", str(tmp_path))
    report = analyze_impact(["shop/catalog.py"])

    assert report["directly_changed_services"] == ["products"]
    assert "GET /products/{product_id}" in {
        item["endpoint"] for item in report["affected_endpoints"]
    }
    assert "tests/test_catalog.py::test_get_product" in report["recommended_nodeids"]
    assert report["analysis"] == "import_graph"
