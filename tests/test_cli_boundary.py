from delivery_fixtures import record_inputs
"""The CLI consumes its inbound reader and reports unavailable source truth."""
from orchestrator.adapters.inbound.cli import main
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.services.delivery_resolution import derive_from_records

class Reader:
    def __init__(self, unavailable=False):
        self.unavailable = unavailable
        self.repos = []

    def execute(self, repo):
        self.repos.append(repo)
        if self.unavailable:
            raise SourceUnavailable("pinned lifecycle unavailable")
        return derive_from_records(repo, True, record_inputs({}))

def test_cli_uses_inbound_reader(capsys):
    reader = Reader()
    assert main(["status", "app"], reader=reader) == 0
    assert reader.repos == ["app"]
    assert "delivery: app" in capsys.readouterr().out

def test_cli_unavailable_reports_failure(capsys):
    assert main(["next", "app"], reader=Reader(True)) == 2
    assert "pinned lifecycle unavailable" in capsys.readouterr().err
