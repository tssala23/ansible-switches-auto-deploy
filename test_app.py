from unittest.mock import patch, Mock
import pytest
import notifier
from pathlib import Path

notify_with_vlan_change = {"commits": [{"modified": ["group_vars/all/vlans.yaml"]}]}

notify_with_switch_change = {
    "commits": [{"modified": ["host_vars/switch1/interfaces.yaml"]}]
}


@pytest.fixture()
def testapp(httpserver):
    class config:
        AUTODEPLOY_REPOURL= "unused-in-testing"
        SLACK_WEBHOOK_URL= httpserver.url_for("/notify")
        VERIFY_WEBHOOK_SIGNATURE= False

    tester = notifier.create_app(config_from_env=False, config=config)


    yield tester


@pytest.fixture()
def client(testapp):
    with patch("notifier.updateRepo"):
        yield testapp.test_client()

# In the following tests we don't actually run ansible, nor do we
# attempt to clone a remote repository. We prevent the latter by
# simplying mocking out the updateRepo method (see the `client`
# fixture, above). For Ansible, we create a mock for the
# `ansible_runner.run` method, and then set explicit return values on
# that mock to get the behavior we want from the code under test.

@patch("notifier.ansible_runner.run")
def test_vlan_change_deploy_success(fake_run, httpserver, testapp, client):
    def handler(req):
        assert "status: successful" in req.data.decode().lower()

    fake_run.return_value = Mock(status="successful", stdout=Path("."))

    httpserver.expect_request("/notify").respond_with_handler(handler)
    res = client.post("/webhook", json=notify_with_vlan_change)
    assert res.status_code == 200
    httpserver.check_assertions()


@patch("notifier.ansible_runner.run")
def test_vlan_change_deploy_failure(fake_run, httpserver, testapp, client):
    def handler(req):
        assert "status: failed" in req.data.decode().lower()

    fake_run.return_value = Mock(status="failed", stdout=Path("."))

    httpserver.expect_request("/notify").respond_with_handler(handler)
    res = client.post("/webhook", json=notify_with_vlan_change)
    assert res.status_code == 200
    httpserver.check_assertions()


@patch("notifier.ansible_runner.run")
def test_switch_change_deploy_success(fake_run, httpserver, testapp, client):
    def handler(req):
        assert "status: successful" in req.data.decode().lower()

    fake_run.return_value = Mock(status="successful", stdout=Path("."))

    httpserver.expect_request("/notify").respond_with_handler(handler)
    res = client.post("/webhook", json=notify_with_switch_change)
    assert res.status_code == 200
    httpserver.check_assertions()


@patch("notifier.ansible_runner.run")
def test_switch_change_deploy_failure(fake_run, httpserver, testapp, client):
    def handler(req):
        assert "status: failed" in req.data.decode().lower()

    fake_run.return_value = Mock(status="failed", stdout=Path("."))

    httpserver.expect_request("/notify").respond_with_handler(handler)
    res = client.post("/webhook", json=notify_with_switch_change)
    assert res.status_code == 200
    httpserver.check_assertions()