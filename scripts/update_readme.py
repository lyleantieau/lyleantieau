"""Rewrites the live deliverables section of README.md from the board.

Only the text between the <!-- deliverables:start --> and <!-- deliverables:end --> markers
is replaced, so everything else in the README can be edited by hand.
"""
import datetime
import json
import os
import re
import sys
import urllib.request

OWNER = "lyleantieau"
BOARD = 1
README = os.path.join(os.path.dirname(__file__), "..", "README.md")
ACTIVE = ["In progress", "Up next", "Waiting on others"]  # display order
PEOPLE = ["Chris", "Alessandro", "Nikolaus", "Brad", "Lab-wide"]  # Requested by options
RECENT_DAYS = 30

QUERY = """
query($owner: String!, $num: Int!, $after: String) {
  user(login: $owner) {
    projectV2(number: $num) {
      url
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          content { ... on Issue { title url state closedAt } }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldDateValue { date field { ... on ProjectV2FieldCommon { name } } }
            }
          }
        }
      }
    }
  }
}
"""


def graphql(variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {os.environ['GH_TOKEN']}"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    if body.get("errors"):
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]["projectV2"]


def fetch_items():
    """Returns (board_url, [item dicts]) for issues on the board, in board order."""
    items, after = [], None
    while True:
        board = graphql({"owner": OWNER, "num": BOARD, "after": after})
        for node in board["items"]["nodes"]:
            issue = node["content"]
            if not issue or "title" not in issue:
                continue  # draft items and pull requests
            fields = {}
            for value in node["fieldValues"]["nodes"]:
                if value and "field" in value:
                    fields[value["field"]["name"]] = value.get("name") or value.get("text") or value.get("date")
            if issue["state"] == "CLOSED":
                fields["Status"] = "Done"
            items.append({**issue, "fields": fields})
        page = board["items"]["pageInfo"]
        if not page["hasNextPage"]:
            return board["url"], items
        after = page["endCursor"]


def cell(text):
    return (text or "").replace("|", "\\|").replace("\n", " ") or "—"


def link(item):
    return f"[{cell(item['title'])}]({item['url']})"


def date(value):
    return datetime.date.fromisoformat(value) if value else None


def short(value):
    return date(value).strftime("%b %-d") if value else "—"


def timeline(fields, today):
    """Start → Target plus how long is left, e.g. "Oct 30 → Nov 6 · 7 days left"."""
    target = date(fields.get("Target"))
    if not target:
        return "—"
    span = f"{short(fields['Start'])} → {short(fields['Target'])}" if fields.get("Start") else f"by {short(fields['Target'])}"
    days = (target - today).days
    if days < 0:
        left = f"⚠️ {-days} day{'s' * (days != -1)} overdue"
    elif days == 0:
        left = "due today"
    else:
        left = f"{days} day{'s' * (days != 1)} left"
    return f"{span} · {left}"


def deliverables_section():
    url, items = fetch_items()
    today = datetime.date.today()
    for i in items:
        i["fields"].setdefault("Status", "Up next")
    active = [i for i in items if i["fields"]["Status"] in ACTIVE]
    active.sort(key=lambda i: ACTIVE.index(i["fields"]["Status"]))  # stable, keeps board rank
    cutoff = today - datetime.timedelta(days=RECENT_DAYS)
    done = [i for i in items if i["fields"]["Status"] == "Done"
            and (i["closedAt"] is None or date(i["closedAt"][:10]) >= cutoff)]

    counts = " · ".join(f"{sum(i['fields']['Status'] == s for i in active)} {s.lower()}" for s in ACTIVE)
    per_person = " · ".join(f"{p} {sum(i['fields'].get('Requested by') == p for i in active)}" for p in PEOPLE)
    lines = [f"{counts} · [full board →]({url})", "", f"**Open items by person:** {per_person}", ""]
    if not active:
        return "\n".join(lines + ["_Nothing queued right now._"])

    lines += ["| # | Deliverable | For | Priority | Status | Timeline |", "|---|---|---|---|---|---|"]
    for n, i in enumerate(active, 1):
        f = i["fields"]
        lines.append(f"| {n} | {link(i)} | {cell(f.get('Requested by'))} | {cell(f.get('Priority'))} "
                     f"| {f['Status']} | {timeline(f, today)} |")
    if done:
        lines += ["", f"<details><summary>Done in the last {RECENT_DAYS} days ({len(done)})</summary>", "",
                  "| Deliverable | For |", "|---|---|"]
        lines += [f"| {link(i)} | {cell(i['fields'].get('Requested by'))} |" for i in done]
        lines += ["", "</details>"]
    return "\n".join(lines)


def replace_section(text, name, body):
    pattern = re.compile(rf"(<!-- {name}:start -->).*?(<!-- {name}:end -->)", re.S)
    if not pattern.search(text):
        sys.exit(f"README is missing the {name} markers")
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", text)


def main():
    with open(README) as f:
        text = f.read()
    text = replace_section(text, "deliverables", deliverables_section())
    with open(README, "w") as f:
        f.write(text)


if __name__ == "__main__":
    main()
