"""
Code Review Environment Implementation.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import CodeReviewAction, CodeReviewObservation, ReviewFinding
except ImportError:
    from models import CodeReviewAction, CodeReviewObservation, ReviewFinding


TASKS = {
    "easy": {
        "task_id": "easy_bugs",
        "difficulty": "easy",
        "description": (
            "Review the following Python function for obvious bugs. "
            "Look for: undefined variables, off-by-one errors, missing return statements, "
            "type errors, and incorrect function calls. Report each issue with its line number."
        ),
        "language": "python",
        "code": '''\
def process_user_records(records):
    """Process a list of user records and return summary statistics."""
    total_age = 0
    valid_count = 0
    names = []

    for i in range(1, len(records)):  # Line 7: off-by-one, skips first record
        record = records[i]

        if record.get("age") and record.get("name"):
            total_age += record["age"]
            valid_count += 1
            names.append(record["name"])

        if record.get("status") == "active":
            active_users += 1  # Line 15: undefined variable active_users

    avg_age = total_age / valid_count  # Line 17: ZeroDivisionError if valid_count is 0

    result = {
        "average_age": avg_age,
        "valid_count": valid_count,
        "names": names,
        "active_count": active_users,  # Line 23: references undefined variable
    }
    # Line 25: missing return statement
''',
        "known_issues": [
            {"id": "easy_1", "line": 7, "type": "bug",
             "keywords": ["off-by-one", "skip", "first", "range(1", "index 0", "starts at 1"]},
            {"id": "easy_2", "line": 15, "type": "bug",
             "keywords": ["undefined", "active_users", "not defined", "undeclared", "NameError"]},
            {"id": "easy_3", "line": 17, "type": "bug",
             "keywords": ["zero", "division", "ZeroDivision", "valid_count is 0", "divide by zero", "empty"]},
            {"id": "easy_4", "line": 25, "type": "bug",
             "keywords": ["return", "missing", "no return", "doesn't return", "None"]},
        ],
    },
    "medium": {
        "task_id": "medium_logic",
        "difficulty": "medium",
        "description": (
            "Review the following Python code for logic errors. "
            "Look for: incorrect algorithm implementation, wrong edge case handling, "
            "flawed conditional logic, and data structure misuse. Report each issue with its line number."
        ),
        "language": "python",
        "code": '''\
def find_duplicates(items):
    """Find all duplicate items in a list. Return list of items that appear more than once."""
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
            seen.remove(item)  # Line 8: removes from seen, so triple occurrences missed
        else:
            seen.add(item)
    return list(duplicates)


def merge_sorted_lists(list1, list2):
    """Merge two sorted lists into one sorted list."""
    result = []
    i, j = 0, 0

    while i < len(list1) and j < len(list2):
        if list1[i] <= list2[j]:
            result.append(list1[i])
            i += 1
        else:
            result.append(list2[j])
            j += 1

    while i < len(list1):
        result.append(list1[i])
        i += 1

    return result  # Line 32: missing remaining elements from list2


def calculate_discount(price, customer_type, quantity):
    """Calculate discounted price based on customer type and quantity."""
    if customer_type == "premium":
        discount = 0.20
    elif customer_type == "regular":
        discount = 0.10
    # Line 40: no else clause - discount undefined for unknown customer types

    if quantity > 100:
        discount += 0.05  # Line 43: may fail if discount undefined
    elif quantity > 50:
        discount += 0.02

    final_price = price * quantity * (1 - discount)

    if final_price < 0:
        final_price = 0

    return final_price
''',
        "known_issues": [
            {"id": "med_1", "line": 8, "type": "logic_error",
             "keywords": ["remove", "triple", "three", "multiple", "occurrences", "seen.remove"]},
            {"id": "med_2", "line": 32, "type": "logic_error",
             "keywords": ["list2", "remaining", "missing", "leftover", "rest of", "second list"]},
            {"id": "med_3", "line": 40, "type": "logic_error",
             "keywords": ["else", "unknown", "customer", "undefined", "discount", "no default", "missing else"]},
            {"id": "med_4", "line": 43, "type": "logic_error",
             "keywords": ["undefined", "discount", "UnboundLocal", "not defined", "fail"]},
        ],
    },
    "hard": {
        "task_id": "hard_security",
        "difficulty": "hard",
        "description": (
            "Review the following Python web application code for security vulnerabilities. "
            "Look for: SQL injection, path traversal, command injection, insecure deserialization, "
            "XSS vulnerabilities, and hardcoded secrets. Report each issue with its line number."
        ),
        "language": "python",
        "code": '''\
import os
import pickle
import sqlite3
import subprocess
from flask import Flask, request, render_template_string

app = Flask(__name__)
DATABASE = "users.db"
SECRET_KEY = "my_super_secret_key_12345"  # Line 9: hardcoded secret

def get_user(username):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{username}'"  # Line 15: SQL injection
    cursor.execute(query)
    user = cursor.fetchone()
    conn.close()
    return user

@app.route("/search")
def search():
    query = request.args.get("q", "")
    html = f"<h1>Results for: {query}</h1>"  # Line 24: XSS
    return render_template_string(html)

@app.route("/download")
def download():
    filename = request.args.get("file", "")
    filepath = os.path.join("/var/data", filename)  # Line 30: path traversal
    with open(filepath, "r") as f:
        return f.read()

@app.route("/run")
def run_command():
    cmd = request.args.get("cmd", "echo hello")
    result = subprocess.run(cmd, shell=True, capture_output=True)  # Line 37: cmd injection
    return result.stdout.decode()

@app.route("/load_session")
def load_session():
    data = request.get_data()
    session = pickle.loads(data)  # Line 42: insecure deserialization
    return str(session)
''',
        "known_issues": [
            {"id": "hard_1", "line": 9, "type": "security_vulnerability",
             "keywords": ["hardcoded", "secret", "SECRET_KEY", "credential", "password", "plaintext"]},
            {"id": "hard_2", "line": 15, "type": "security_vulnerability",
             "keywords": ["SQL", "injection", "f-string", "format", "parameterized", "unsanitized"]},
            {"id": "hard_3", "line": 24, "type": "security_vulnerability",
             "keywords": ["XSS", "cross-site", "script", "unescaped", "render_template_string", "user input"]},
            {"id": "hard_4", "line": 30, "type": "security_vulnerability",
             "keywords": ["path", "traversal", "directory", "../", "join", "arbitrary file"]},
            {"id": "hard_5", "line": 37, "type": "security_vulnerability",
             "keywords": ["command", "injection", "shell=True", "subprocess", "os.system", "arbitrary"]},
            {"id": "hard_6", "line": 42, "type": "security_vulnerability",
             "keywords": ["pickle", "deserialization", "insecure", "arbitrary code", "untrusted"]},
        ],
    },
}


LINE_TOLERANCE = 3

EPS = 1e-6

def _match_issue(finding, known):
    score = 0.0
    feedback_parts = []
    line_diff = abs(finding.line_number - known["line"])
    if line_diff == 0:
        score += 0.3
        feedback_parts.append("Exact line match (+0.3)")
    elif line_diff <= LINE_TOLERANCE:
        proximity_score = 0.2 * (1 - line_diff / (LINE_TOLERANCE + 1))
        score += proximity_score
        feedback_parts.append(f"Close line match, off by {line_diff} (+{proximity_score:.2f})")
    else:
        return 0.0, "Line number too far from any known issue"

    desc_lower = (finding.description + " " + finding.suggested_fix).lower()
    matched_keywords = sum(1 for kw in known["keywords"] if kw.lower() in desc_lower)
    if matched_keywords > 0:
        keyword_score = min(0.5, 0.15 * matched_keywords)
        score += keyword_score
        feedback_parts.append(f"Matched {matched_keywords} keywords (+{keyword_score:.2f})")
    else:
        score += 0.05
        feedback_parts.append("Issue location correct but description unclear (+0.05)")

    if finding.issue_type.lower().replace(" ", "_") == known["type"]:
        score += 0.1
        feedback_parts.append("Correct issue type (+0.1)")

    if finding.suggested_fix and len(finding.suggested_fix) > 10:
        score += 0.1
        feedback_parts.append("Provided suggested fix (+0.1)")

    return min(score, 1.0), "; ".join(feedback_parts)


def grade_review(findings, task_key):
    task = TASKS[task_key]
    known_issues = task["known_issues"]
    num_known = len(known_issues)

    if not findings:
        return EPS, "No findings submitted. The code has issues.", 0

    used_known = set()
    used_findings = set()
    all_pairs = []
    for fi, finding in enumerate(findings):
        for ki, known in enumerate(known_issues):
            score, fb = _match_issue(finding, known)
            if score > 0:
                all_pairs.append((score, fi, ki, fb))

    all_pairs.sort(key=lambda x: -x[0])
    matches = []
    for score, fi, ki, fb in all_pairs:
        if fi not in used_findings and ki not in used_known:
            matches.append((score, fi, ki, fb))
            used_findings.add(fi)
            used_known.add(ki)

    total_issue_reward = sum(score for score, _, _, _ in matches)
    correct_count = len(matches)
    issue_reward = total_issue_reward / num_known

    false_positives = len(findings) - correct_count
    fp_penalty = false_positives * 0.05

    coverage_bonus = 0.1 if correct_count == num_known else 0.0

    total_reward = max(EPS, min(1.0 - EPS, issue_reward - fp_penalty + coverage_bonus))

    feedback_lines = [f"Found {correct_count}/{num_known} known issues."]
    for score, fi, ki, fb in matches:
        feedback_lines.append(f"  Issue '{known_issues[ki]['id']}': {fb} (score: {score:.2f})")
    if false_positives > 0:
        feedback_lines.append(f"  {false_positives} false positive(s) (-{fp_penalty:.2f})")
    if coverage_bonus > 0:
        feedback_lines.append(f"  Full coverage bonus (+{coverage_bonus:.2f})")
    feedback_lines.append(f"Total reward: {total_reward:.2f}")

    missed = [known_issues[ki]["id"] for ki in range(num_known) if ki not in used_known]
    if missed:
        feedback_lines.append(f"Missed issues: {', '.join(missed)}")

    return total_reward, "\n".join(feedback_lines), correct_count


TASK_ORDER = ["easy", "medium", "hard"]


class CodeReviewEnvironment(Environment):
    """
    Code Review RL Environment.

    Supports two modes:
    1. CURRENT_TASK env var set -> single task per episode (used by inference.py)
    2. No env var -> serves tasks via HTTP, cycling through easy/medium/hard
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True
    _class_counter = 0

    def __init__(self):
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._done = False

        # Determine which task to serve
        task_name = os.environ.get("CURRENT_TASK", "")
        if task_name in TASKS:
            self._task_key = task_name
        else:
            self._task_key = TASK_ORDER[
                CodeReviewEnvironment._class_counter % len(TASK_ORDER)
            ]
            CodeReviewEnvironment._class_counter += 1

        self._task = TASKS[self._task_key]

    def reset(self) -> CodeReviewObservation:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._done = False

        # Re-check task on reset
        task_name = os.environ.get("CURRENT_TASK", "")
        if task_name in TASKS:
            self._task_key = task_name
        else:
            self._task_key = TASK_ORDER[
                CodeReviewEnvironment._class_counter % len(TASK_ORDER)
            ]
            CodeReviewEnvironment._class_counter += 1

        self._task = TASKS[self._task_key]

        return CodeReviewObservation(
            task_id=self._task["task_id"],
            task_description=self._task["description"],
            difficulty=self._task["difficulty"],
            code_to_review=self._task["code"],
            language=self._task["language"],
            num_known_issues=len(self._task["known_issues"]),
            feedback="Review the code and submit your findings.",
            issues_found_so_far=0,
            done=False,
            reward=0.0,
        )

    def step(self, action: CodeReviewAction) -> CodeReviewObservation:
        self._state.step_count += 1

        if self._done:
            return CodeReviewObservation(
                task_id=self._task["task_id"],
                task_description="",
                difficulty=self._task["difficulty"],
                code_to_review="",
                language="python",
                num_known_issues=0,
                feedback="Already done. Call reset() for next task.",
                issues_found_so_far=0,
                done=True,
                reward=0.0,
            )

        reward, feedback, correct = grade_review(action.findings, self._task_key)
        self._done = True

        return CodeReviewObservation(
            task_id=self._task["task_id"],
            task_description=self._task["description"],
            difficulty=self._task["difficulty"],
            code_to_review="",
            language=self._task["language"],
            num_known_issues=len(self._task["known_issues"]),
            feedback=feedback,
            issues_found_so_far=correct,
            done=True,
            reward=reward,
            metadata={"task": self._task_key, "score": reward},
        )

    @property
    def state(self) -> State:
        return self._state