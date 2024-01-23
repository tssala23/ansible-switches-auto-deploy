from unittest.mock import patch, Mock
import pytest
import notifier
from pathlib import Path

notify_with_vlan_change = {
    "commits": [{"modified": ["group_vars/all/vlans.yaml"]}],
    "head_commit": {"id": "b7b84665d4a848dfd57980348fc04c0392a63bb7"},
}

notify_with_switch_change = {
    "commits": [{"modified": ["host_vars/switch1/interfaces.yaml"]}],
    "head_commit": {"id": "b7b84665d4a848dfd57980348fc04c0392a63bb7"},
}


@pytest.fixture()
def testapp(httpserver):
    class config:
        AUTODEPLOY_REPOURL = "unused-in-testing"
        SLACK_WEBHOOK_URL = httpserver.url_for("/notify")
        VERIFY_WEBHOOK_SIGNATURE = False

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


@pytest.mark.parametrize(
    "payload,expected_text",
    (
        (notify_with_vlan_change, "successful"),
        (notify_with_vlan_change, "failed"),
        (notify_with_switch_change, "successful"),
        (notify_with_switch_change, "failed"),
    ),
)
@patch("notifier.ansible_runner.run")
def test_vlan_change_deploy_success(
    fake_run, payload, expected_text, tmp_path, httpserver, testapp, client
):
    def handler(req):
        assert f"status: {expected_text}" in req.data.decode().lower()

    stdout_path = tmp_path / "stdout.txt"
    with stdout_path.open("w") as fd:
        fd.write("This is a test")
    with stdout_path.open() as fd:
        fake_run.return_value = Mock(status=expected_text, stdout=fd)

        httpserver.expect_request("/notify").respond_with_handler(handler)
        res = client.post(
            "/webhook",
            json=payload,
            headers={"x-github-event": "push"},
        )
        assert res.status_code == 200
        httpserver.check_assertions()
