from flask import Flask, request, current_app, abort
import git
from git import Repo
import ansible_runner
import os
import requests
import json
import logging
import slack
import github


class CONFIG_DEFAULTS:
    COLOR_SUCCESS = "#05eb2f"
    COLOR_FAILURE = "#f00216"
    VERIFY_WEBHOOK_SIGNATURE = False

class ConfigurationError(Exception):
    pass


def require_config(app, name):
    if name not in app.config:
        raise ConfigurationError(f"missing {name}")



def updateRepo(repoDir, repoURL, commitID):
    """Clone or update the local git repository"""
    if os.path.isdir(
        repoDir
    ):  # If the clone of the repo exists pull updates, if not clone it
        repo = Repo(repoDir)
        o = repo.remotes.origin
        o.pull()
        repo.git.checkout(commitID)
        current_app.logger.info("pulled changes for %s", repoURL)
    else:
        repo = Repo.clone_from(repoURL, repoDir, no_checkout=True)
        repo.git.checkout(commitID)
        current_app.logger.info("clone %s", repoURL)


def fileChanges(
    commits,
):
    """Returns bool for if vlan file changes and list of individual switch changes"""
    vlanChange = False  # Vlan Flag
    switchChanges = []  # List of modified switches

    for commit in commits:  # Look at each commit in push to main branch
        for path in commit["modified"]:  # Look at the files modified in each commit
            if path == "group_vars/all/vlans.yaml":
                vlanChange = True

            elif path.startswith("host_vars") and path.endswith("interfaces.yaml"):
                switchChanges.append(path.split("/")[1])

        current_app.logger.info(
            "Vlan change: %s Switch changes: %s", vlanChange, switchChanges
        )

        for path in commit.get("added", []):
            switchChanges.append(path.split("/")[1])

    return (vlanChange, switchChanges)


def runAnsible(repoDir, vlanFlag, switchList):
    """Run the deployment playbook"""
    playbook = current_app.config.get("AUTODEPLOY_PLAYBOOK", "deploy.yaml")

    if (
        vlanFlag
    ):  # If the vlanFlag is true run playbook on all switches else only on switches with changes
        res = ansible_runner.run(
            private_data_dir=repoDir,
            playbook=playbook,
        )
        current_app.logger.info("Vlan change, all switches update.")

    else:
        strSwitchList = ",".join(
            str(switch) for switch in switchList # map(str, switchList)
        )  # Convert the list to string, items seperated by commas
        res = ansible_runner.run(
            private_data_dir=repoDir,
            playbook=playbook,
            limit=strSwitchList,  # equivalent to --limit
        )
        current_app.logger.info("Individual switch change: %s", strSwitchList)
    return (res.status, res.stdout)


def sendAlert(vlanFlag, switchList, status, stdoutPath, webhook_url):
    """Send notification to slack channel"""
    strSwitchList = ",".join(
        str(switch) for switch in switchList # map(str, switchList)
    )  # Convert the list to string, items seperated by commas

    if status == "failed":
        color = current_app.config["COLOR_FAILURE"]
    else:
        color = current_app.config["COLOR_SUCCESS"]

    if (
        vlanFlag
    ):  # Create the messages for the alerts, different depending on what switches were changed
        # LKS: Here (and elsewhere) we should probably look into using
        # python f-strings rather than string concatenation.
        change_message = "All switches were changed."
    else:
        change_message = f"Switches: {strSwitchList}"
    
    if "X-GitHub-Event" not in request.headers:
        abort(400, "Missing x-github-event header")

    if request.headers["X-GitHub-Event"] == "ping":
        return {"status": "ping successful"}

    if request.headers["X-GitHub-Event"] != "push":
        abort(400, "Unsupported event")

    message = slack.SlackMessage(
        blocks=[
            slack.SlackHeaderBlock(
                text=slack.SlackText(text=f"Switch Notification")
            ),
            slack.SlackSectionBlock(
                text=slack.SlackMarkdown(
                    text=f"Changes detected in switch configuration.\nEffected switches:{change_message}\nStatus: {status}"
                )
            ),
        ],
    )

    """message.attachments = [
        slack.SlackAttachment(
            blocks=[
                slack.SlackSectionBlock(
                    text=slack.SlackMarkdown(text=f"```\n{stdoutPath}\n```")
                ),
            ]
        ),
    ]"""

    if current_app.notifier:
            try:
                current_app.notifier.notify(message)
                current_app.logger.info("Slack notification sent")
            except slack.SlackException as err:
                current_app.logger.error("slack notification failed: %s", err)
    return "success", 200



def create_app(config_from_env=True, config=None):
    """Create and configure flask application"""
    app = Flask(__name__)

    # Configure application:
    #   Defaults ->
    #     Environment ->
    #       Explicit config
    app.config.from_object(CONFIG_DEFAULTS)
    if config_from_env:
        app.config.from_prefixed_env()
    app.config.from_object(config)

    require_config(app, "SLACK_WEBHOOK_URL")
    app.notifier = slack.SlackNotifier(app.config["SLACK_WEBHOOK_URL"])

    if app.config.get("VERIFY_WEBHOOK_SIGNATURE", True):
        require_config(app, "GITHUB_WEBHOOK_SECRET")
        app.verifier = github.GithubSignatureVerifier(
            app.config["GITHUB_WEBHOOK_SECRET"]
        )
    else:
        app.verifier = github.GithubNullVerifier()

    @app.route("/healthz", methods=["GET"])
    def healthz():
        return "OK"

    @app.route("/webhook", methods=["POST"])
    def handle_push_notification():
        try:
            current_app.verifier.verify_webhook_signature(request)
        except github.WebhookSignatureError as err:
            current_app.logger.error(f"invalid signature: {err}")
            abort(400, "Bad signature")

        current_app.logger.info("received valid notification from github")

        repoURL = current_app.config["AUTODEPLOY_REPOURL"]
        repoDir = current_app.config.get(
            "AUTODEPLOY_REPODIR", os.path.basename(repoURL)
        )
        webhookURL = current_app.config["SLACK_WEBHOOK_URL"]

        current_app.logger.info("received webhook")

        vlanFlag, switchList = fileChanges(request.json["commits"])
        if vlanFlag or switchList:
            current_app.logger.info("changes detected")

            commitID = request.json["head_commit"]["id"]
            updateRepo(repoDir, repoURL, commitID)
            status, stdoutPath = runAnsible(repoDir, vlanFlag, switchList)

            current_app.logger.info("sending notification to %s", webhookURL)
            sendAlert(vlanFlag, switchList, status, stdoutPath, webhookURL)
        return "success", 200

    @app.before_request
    def configure_logging():
        logging.basicConfig(level=current_app.config.get("LOGLEVEL", "INFO"))

    return app

