from flask import Flask, request, abort
from git import Repo
import ansible_runner
import os
import requests
import json
import configparser

from datetime import datetime

app = Flask(__name__)

def appendTime(message):
    output = "[" + datetime.utcnow().isoformat() + "]" + " " + message
    return (output)

def updateRepo(repoName, repoURL): #Update the local git repo

    if os.path.isdir(repoName): #If the clone of the repo exists pull updates, if not clone it 
        repo = Repo(repoName)
        o = repo.remotes.origin
        o.pull()
        print(appendTime("Repo Pulled"))
    else:
        Repo.clone_from(repoURL, repoName)
        print(appendTime("Repo Cloned"))

def fileChanges(commits): #Returns bool for if vlan file changes and list of individual switch changes
    
    vlanChange = False #Vlan Flag
    switchChanges = [] #List of modified switches

    for commit in commits: #Look at each commit in push to main branch
        
        for file in commit['modified']: #Look at the files modified in each commit
            split = file.split("/")
            
            if split[2] == 'vlans.yaml' : #Set flag to true if vlan change
                vlanChange = True
                
            elif split[0] == 'host_vars' : #Add all changed switches to a list 
                switchChanges.append(split[1]) #Adds switch name to list

    print(appendTime("Vlan change: " + vlanChange + "\nSwitch chnages: " + switchChanges))

    return(vlanChange, switchChanges)

def runAnsible(vlanFlag, switchList): #Function for running ansible playbook
    if vlanFlag: #If the vlanFlag is true run playbook on all switches else only on switches with changes
        runAll = ansible_runner.run(
            private_data_dir='ansible-switches/',
            playbook='deploy.yaml'
         )
        print(appendTime("Vlan change, all switches update."))
        return(runAll.status, runAll.stdout)

    else:
        strSwitchList = ','.join(map(str,switchList)) #Convert the list to string, items seperated by commas
        runSwitches = ansible_runner.run(
            private_data_dir='ansible-switches/',
            playbook='deploy.yaml',
            limit= strSwitchList #equivalent to --limit
        )
        print(appendTime("Individual switch change. " + strSwitchList + " switches update."))
        return(runSwitches.status, runSwitches.stdout)
    
def sendAlert(vlanFlag, switchList, status, stdoutPath, webhook_url): #Function to send notification to slack channel

    strSwitchList = ','.join(map(str,switchList)) #Convert the list to string, items seperated by commas

    if status == 'failed':
        color = '#f00216' #red color
        title = ("Switch Change :large_red_square:")
    else:
        color = '#05eb2f' #green color
        title = ("Switch Change :large_green_square:")

    if vlanFlag: #Create the messages for the alerts, different depending on what switches were changed
        message = 'Change made to switches.\nAll switches were changed.\nStatus:' + status + '\nPath to stdout: ' + str(stdoutPath.name)
    else:
        message = 'Change made to switches.\nSwitches: \n' + strSwitchList + '\nStatus: ' + status + '\nPath to stdout: ' + str(stdoutPath.name)

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
                ]
            }
        ]
    }

    headers = {
        'Content-Type': "application/json",
    }

    response = requests.post(
        webhook_url,
        data=json.dumps(slack_data),
        headers=headers
    )

    print(appendTime(response.text))
        
@app.route('/webhook', methods=['POST'])
def webhook():
    config = configparser.ConfigParser()
    config.read('config.ini')
    repoName = config['AUTODEPLOY']['RepoName']
    repoURL = config['AUTODEPLOY']['RepoURL']
    webhookURL = config['AUTODEPLOY']['WebhookURL']

    if request.method == 'POST':

        print(appendTime("Recieved Webhook"))

        vlanFlag, switchList = fileChanges(request.json['commits'])
        if vlanFlag or switchList:

            print(appendTime("Changes detected"))

            updateRepo(repoName, repoURL)
            status, stdoutPath = runAnsible(vlanFlag, switchList)
            sendAlert(vlanFlag, switchList, status, stdoutPath, webhookURL)
        return 'success', 200
        
    else:
        abort(400)

if __name__ == '__main__':
    app.run()