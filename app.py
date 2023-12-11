from flask import Flask, request, current_app
from git import Repo
import ansible_runner
import os
import requests
import json
import logging


class CONFIG_DEFAULTS:
    COLOR_SUCCESS = "#05eb2f"
    COLOR_FAILURE = "#f00216"


def updateRepo(repoDir, repoURL):
    """Clone or update the local git repository"""
    if os.path.isdir(
        repoDir
    ):  # If the clone of the repo exists pull updates, if not clone it
        repo = Repo(repoDir)
        o = repo.remotes.origin
        o.pull()
        current_app.logger.info("pulled changes for %s", repoURL)
    else:
        Repo.clone_from(repoURL, repoDir)
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
            map(str, switchList)
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
        map(str, switchList)
    )  # Convert the list to string, items seperated by commas

    if status == "failed":
        color = current_app.config["COLOR_FAILURE"]
        title = "Switch Change :large_red_square:"
    else:
        color = current_app.config["COLOR_SUCCESS"]
        title = "Switch Change :large_green_square:"

    if (
        vlanFlag
    ):  # Create the messages for the alerts, different depending on what switches were changed
        # LKS: Here (and elsewhere) we should probably look into using
        # python f-strings rather than string concatenation.
        message = (
            "Change made to switches.\nAll switches were changed.\nStatus: "
            + status
            + "\nPath to stdout: "
            + str(stdoutPath.name)
        )
    else:
        message = (
            "Change made to switches.\nSwitches: \n"
            + strSwitchList
            + "\nStatus: "
            + status
            + "\nPath to stdout: "
            + str(stdoutPath.name)
        )

    slack_data = {
        "username": "SwitchAlert",
        "icon_emoji": ":bulb:",
        "channel": "#webhook-testing",
        "attachments": [
            {
                "color": color,
                "fields": [
                    {
                        "title": title,
                        "value": message,
                        "short": "false",
                    }
                ],
            }
        ],
    }

    headers = {
        "Content-Type": "application/json",
    }

    response = requests.post(webhook_url, data=json.dumps(slack_data), headers=headers)

    current_app.logger.info("notify response: %s", response.text)


def create_app(config_from_env=True):
    """Create and configure flask application"""
    app = Flask(__name__)
    app.config.from_object(CONFIG_DEFAULTS)

    if config_from_env:
        app.config.from_prefixed_env()

    @app.route("/webhook", methods=["POST"])
    def webhook():
        repoURL = current_app.config["AUTODEPLOY_REPOURL"]
        repoDir = current_app.config.get(
            "AUTODEPLOY_REPODIR", os.path.basename(repoURL)
        )
        webhookURL = current_app.config["AUTODEPLOY_WEBHOOKURL"]

        current_app.logger.info("received webhook")

        vlanFlag, switchList = fileChanges(request.json["commits"])
        if vlanFlag or switchList:
            current_app.logger.info("changes detected")

            updateRepo(repoDir, repoURL)
            status, stdoutPath = runAnsible(repoDir, vlanFlag, switchList)

            current_app.logger.info("sending notification to %s", webhookURL)
            sendAlert(vlanFlag, switchList, status, stdoutPath, webhookURL)
        return "success", 200

    @app.before_request
    def configure_logging():
        logging.basicConfig(level=current_app.config.get("LOGLEVEL", "INFO"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run()
