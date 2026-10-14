from orchestrator.domain.model.app_lifecycle_result import AppLifecycleResult
from orchestrator.domain.model.platform_app import PlatformApp
"""Studio lifecycle ops: the Console pauses and resumes platform apps by delegating to
platform-studio, then refreshes the fleet so the live status reflects it. Audit: csd-intent ."""
from capability_support import command_kwargs
from pytest_intent import intent
from capability_support import make_capabilities

class FakeRepos:

    def list_delivery_repos(self):
        return []

class FakeGateway:

    def __init__(self):
        self.calls = []

    def health(self):
        return []

    def artifacts_for(self, slug):
        return {}

    def platform_apps(self):
        return [PlatformApp(name='app1', repository='example-org/app1', onboarded=True, status='running', hostname='', revision='', role=None)]

    def pause_app(self, name):
        self.calls.append(('pause', name))
        return AppLifecycleResult(name, True, 'paused')

    def resume_app(self, name):
        self.calls.append(('resume', name))
        return AppLifecycleResult(name, False, 'running')

@intent('INT-FC-R41')
def test_pause_and_resume_delegate_to_platform_studio():
    gw = FakeGateway()
    svc = make_capabilities(FakeRepos(), studios=gw)
    assert svc.pause_app.execute('app1', **command_kwargs('example-org/app1')).status == 'paused'
    assert svc.resume_app.execute('app1', **command_kwargs('example-org/app1')).status == 'running'
    assert gw.calls == [('pause', 'app1'), ('resume', 'app1')]


def test_lifecycle_commands_refuse_an_ambiguous_repository_before_dispatch():
    import pytest
    from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

    class AmbiguousGateway(FakeGateway):
        def platform_apps(self):
            return [PlatformApp("app1", "app1")]

    gateway = AmbiguousGateway()
    service = make_capabilities(FakeRepos(), studios=gateway)
    for command in (service.pause_app, service.resume_app):
        with pytest.raises(SourceUnavailable, match="owner"):
            command.execute("app1", **command_kwargs("example-org/app1"))
    assert gateway.calls == []
