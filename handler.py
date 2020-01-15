from git import Repo
from loguru import logger
from uuid import uuid4
from github import Github
import subprocess
from os import scandir
from github import Github
import simplejson as json

import boto3

ssm = boto3.client('ssm')

token = ssm.get_parameter(Name='auth_token', WithDecryption=True).get('Parameter').get('Value')

gh = Github(token)


def check_python_files(event, context):
    data = event
    if (
        "action" in data
        and data["action"] == "opened"
        and "pull_request" in data
        and "repository" in data
    ):
        repo = gh.get_repo(data["repository"]["full_name"])
        target_pr = repo.get_pull(data["number"])
        branch = data["pull_request"]["head"]["ref"]
        url = data.get("pull_request").get("head").get("repo").get("html_url")
        affected_files = target_pr.get_files()
        presence_python_files = False
        presence_req = False
        pr_id = data.get("number")
        print(repo, target_pr, branch, url, pr_id)
        if any(str(single.filename).endswith(".py") for single in affected_files):
            presence_python_files = True
        else:
            pass

        if any(single.filename == "requirements.txt" for single in affected_files):
            presence_req = True
        else:
            pass

        return_dict = {
            "branch": branch,
            "repo": url,
            "is_python": presence_python_files,
            "is_requirements": presence_req,
            "pr_id": pr_id,
            "req_repo_path": data["repository"]["full_name"],
        }

        print(return_dict)

        return return_dict
    else:
        return None


def run_bandit(event, context):
    # return event
    data = event  # json.loads(event.get('body'))
    if data:
        if data.get("repo") and data.get("branch") and data.get("is_python"):
            random_val = str(uuid4())
            repo = Repo.clone_from(
                data.get("repo"),
                "/tmp/{}".format(random_val),
                branch=data.get("branch"),
            )
            subprocess.call(
                "/var/lang/bin/python -m bandit -r -f json -o /tmp/result.json /tmp/{}/".format(
                    random_val
                ),
                shell=True,
            )
            with open("/tmp/result.json", "r") as res:
                outcontent = json.loads(res.read())

            data["result"] = outcontent.get("results")

            return data
        else:
            logger.error(
                "Mandatory keys 'repo' and 'branch' not in event body. Will not work"
            )
            return event
    else:
        return None


def run_safety(event, context):
    data = event
    if data:
        if data.get("repo") and data.get("branch"):
            random_val = str(uuid4())
            repo = Repo.clone_from(
                data.get("repo"),
                "/tmp/{}/".format(random_val),
                branch=data.get("branch"),
            )
            for entry in scandir("/tmp/{}/".format(random_val)):
                print(entry)
                if "requirements" in entry.name:
                    print("in loop")
                    subprocess.call(
                        "/var/lang/bin/python -m safety check -r {} --full-report --json -o /tmp/result.json".format(
                            entry.path
                        ),
                        shell=True,
                    )
                    with open("/tmp/result.json", "r") as res:
                        outcontent = json.loads(res.read())

                    data["sca"] = outcontent
                    break

            return data
        else:
            logger.error(
                "Mandatory keys 'repo' and 'branch' not in event body. Will not work"
            )
            return None
    else:
        return None


def sast_pr_comment(event, context):
    if "result" in event:
        mdh1 = "## Static Analysis Report - Bandit\n\n"
        mdtable = "| Issue | File | Line | Confidence | Severity |\n"
        mdheader = "|-------|:----------:|------:|------:|------:|\n"
        mdlist = []
        mdlist.append(mdh1)
        mdlist.append(mdtable)
        mdlist.append(mdheader)
        if isinstance(event["result"], list):
            for single in event["result"]:
                mdlist.append(
                    "| {} | {} | {} | {} | {} |\n".format(
                        single["issue_text"],
                        single["filename"],
                        single["line_number"],
                        single["issue_confidence"],
                        single["issue_severity"],
                    )
                )
            final_md = "".join(mdlist)
            repo = gh.get_repo(event.get("req_repo_path"))
            pr = repo.get_pull(event.get("pr_id"))
            pr.create_issue_comment(final_md)
    return event


def sca_pr_comment(event, context):
    if "sca" in event:
        mdh1 = "## Source Composition Analysis - Safety\n\n"
        mdtable = "| Library | Affected Version | Fix Version | Description | \n"
        mdheader = "|-------|:----------:|------:|------:|\n"
        mdlist = []
        mdlist.append(mdh1)
        mdlist.append(mdtable)
        mdlist.append(mdheader)
        if isinstance(event["sca"], list):
            for single in event["sca"]:
                mdlist.append(
                    "| {} | {} | {} | {} |\n".format(
                        single[0], single[1], single[2], single[3]
                    )
                )
            final_md = "".join(mdlist)
            repo = gh.get_repo(event.get("req_repo_path"))
            pr = repo.get_pull(event.get("pr_id"))
            pr.create_issue_comment(final_md)
    return event
