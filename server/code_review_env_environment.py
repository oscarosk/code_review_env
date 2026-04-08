"""
Code Review Environment Implementation.

An RL environment where an AI agent reviews code snippets for bugs, logic errors,
and security vulnerabilities. The agent receives partial rewards for correctly
identifying issues, their locations, and suggesting fixes.

Tasks:
  - easy: Find obvious bugs (undefined vars, off-by-one, missing returns)
  - medium: Find logic errors (wrong algorithm, bad edge cases)
  - hard: Find security vulnerabilities (SQL injection, path traversal, etc.)
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import CodeReviewAction, CodeReviewObservation, ReviewFinding
except ImportError:
    from models import CodeReviewAction, CodeReviewObservation, ReviewFinding


# ---------------------------------------------------------------------------
# Task definitions: each task has code, known issues, and grading criteria
# ---------------------------------------------------------------------------

TASKS = {
    # ===== EASY: Obvious bugs =====
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

    for i in range(1, len(records)):  # Line 6: off-by-one, skips first record
        record = records[i]

        if record.get("age") and record.get("name"):
            total_age += record["age"]
            valid_count += 1
            names.append(record["name"])

        if record.get("status") == "active":
            active_users += 1  # Line 14: undefined variable active_users

    avg_age = total_age / valid_count  # Line 16: ZeroDivisionError if valid_count is 0

    result = {
        "average_age": avg_age,
        "valid_count": valid_count,
        "names": names,
        "active_count": active_users,  # Line 22: references undefined variable
    }
    # Line 24: missing return statement
''',
        "known_issues": [
            {
                "id": "easy_1",
                "line": 6,
                "type": "bug",
                "keywords": ["off-by-one", "skip", "first", "range(1", "index 0", "starts at 1"],
                "description": "Loop starts at index 1, skipping the first record",
            },
            {
                "id": "easy_2",
                "line": 14,
                "type": "bug",
                "keywords": ["undefined", "active_users", "not defined", "undeclared", "NameError"],
                "description": "Variable active_users is used but never defined",
            },
            {
                "id": "easy_3",
                "line": 16,
                "type": "bug",
                "keywords": ["zero", "division", "ZeroDivision", "valid_count is 0", "divide by zero", "empty"],
                "description": "Division by zero when valid_count is 0",
            },
            {
                "id": "easy_4",
                "line": 24,
                "type": "bug",
                "keywords": ["return", "missing", "no return", "doesn't return", "None"],
                "description": "Function has no return statement, returns None",
            },
        ],
    },
    # ===== MEDIUM: Logic errors =====
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
            seen.remove(item)  # Line 8: removes from seen, so triple occurrences won't be caught
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

    # Line 27-28: Only appends remaining from list1, forgets list2
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
    # Line 39-40: no else clause - discount undefined for unknown customer types

    if quantity > 100:
        discount += 0.05  # Line 42: may fail if discount undefined
    elif quantity > 50:
        discount += 0.02

    final_price = price * quantity * (1 - discount)

    if final_price < 0:  # Line 47: wrong check - discount > 1.0 not prevented
        final_price = 0

    return final_price
''',
        "known_issues": [
            {
                "id": "med_1",
                "line": 8,
                "type": "logic_error",
                "keywords": ["remove", "triple", "three", "multiple", "occurrences", "seen.remove"],
                "description": "Removing from seen means items appearing 3+ times won't all be caught as duplicates",
            },
            {
                "id": "med_2",
                "line": 32,
                "type": "logic_error",
                "keywords": ["list2", "remaining", "missing", "leftover", "rest of", "second list"],
                "description": "Missing while loop to append remaining elements from list2",
            },
            {
                "id": "med_3",
                "line": 40,
                "type": "logic_error",
                "keywords": ["else", "unknown", "customer", "undefined", "discount", "no default", "missing else"],
                "description": "No else clause for unknown customer types; discount will be undefined",
            },
            {
                "id": "med_4",
                "line": 42,
                "type": "logic_error",
                "keywords": ["undefined", "discount", "UnboundLocal", "not defined", "fail"],
                "description": "discount += 0.05 will fail with UnboundLocalError if customer_type is unknown",
            },
        ],
    },
    # ===== HARD: Security vulnerabilities =====
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
    """Fetch user from database."""
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
    html = f"<h1>Results for: {query}</h1>"  # Line 24: XSS - unescaped user input
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
    result = subprocess.run(cmd, shell=True, capture_output=True)  # Line 37: command injection
    return result.stdout.decode()

@app.route("/load_session")
def load_session():
    data = request.get_data()
    session = pickle.loads(data)  # Line 42: insecure deserialization
    return str(session)
''',
        "known_issues": [
            {
                "id": "hard_1",
                "line": 9,
                "type": "security_vulnerability",
                "keywords": ["hardcoded", "secret", "SECRET_KEY", "credential", "password", "plaintext"],
                "description": "Hardcoded secret key in source code",
            },
            {
                "id": "hard_2",
                "line": 15,
                "type": "security_vulnerability",
                "keywords": ["SQL", "injection", "f-string", "format", "parameterized", "unsanitized"],
                "description": "SQL injection via string formatting in query",
            },
            {
                "id": "hard_3",
                "line": 24,
                "type": "security_vulnerability",
                "keywords": ["XSS", "cross-site", "script", "unescaped", "render_template_string", "user input"],
                "description": "Cross-site scripting (XSS) via unescaped user input in HTML",
            },
            {
                "id": "hard_4",
                "line": 30,
                "type": "security_vulnerability",
                "keywords": ["path", "traversal", "directory", "../", "join", "arbitrary file"],
                "description": "Path traversal vulnerability allows reading arbitrary files",
            },
            {
                "id": "hard_5",
                "line": 37,
                "type": "security_vulnerability",
                "keywords": ["command", "injection", "shell=True", "subprocess", "os.system", "arbitrary"],
                "description": "Command injection via shell=True with user input",
            },
            {
                "id": "hard_6",
                "line": 42,
                "type": "security_vulnerability",
                "keywords": ["pickle", "deserialization", "insecure", "arbitrary code", "untrusted"],
                "description": "Insecure deserialization with pickle on untrusted data",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Grading logic
# ---------------------------------------------------------------------------

LINE_TOLERANCE = 3  # Allow ±3 lines for matching


def _match_issue(finding: ReviewFinding, known: Dict[str, Any]) -> Tuple[float, str]:
    """Grade a single finding against a known issue. Returns (score, feedback)."""
    score = 0.0
    feedback_parts = []

    # Check line number proximity
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

    # Check if description matches (keyword matching)
    desc_lower = (finding.description + " " + finding.suggested_fix).lower()
    matched_keywords = sum(1 for kw in known["keywords"] if kw.lower() in desc_lower)
    if matched_keywords > 0:
        keyword_score = min(0.5, 0.15 * matched_keywords)
        score += keyword_score
        feedback_parts.append(f"Matched {matched_keywords} keywords (+{keyword_score:.2f})")
    else:
        score += 0.05
        feedback_parts.append("Issue location correct but description unclear (+0.05)")

    # Check issue type
    if finding.issue_type.lower().replace(" ", "_") == known["type"]:
        score += 0.1
        feedback_parts.append("Correct issue type (+0.1)")

    # Check suggested fix
    if finding.suggested_fix and len(finding.suggested_fix) > 10:
        score += 0.1
        feedback_parts.append("Provided suggested fix (+0.1)")

    return min(score, 1.0), "; ".join(feedback_parts)


def grade_review(findings: List[ReviewFinding], task_key: str) -> Tuple[float, str, int]:
    """
    Grade a complete code review submission.

    Returns:
        (total_reward, feedback_string, num_correct_issues)
    """
    task = TASKS[task_key]
    known_issues = task["known_issues"]
    num_known = len(known_issues)

    if not findings:
        return 0.0, "No findings submitted. The code has issues — look more carefully.", 0

    # Match findings to known issues (greedy best-match)
    used_known = set()
    used_findings = set()
    matches = []

    # Score all possible pairs
    all_pairs = []
    for fi, finding in enumerate(findings):
        for ki, known in enumerate(known_issues):
            score, fb = _match_issue(finding, known)
            if score > 0:
                all_pairs.append((score, fi, ki, fb))

    # Sort by score descending, greedily assign
    all_pairs.sort(key=lambda x: -x[0])
    for score, fi, ki, fb in all_pairs:
        if fi not in used_findings and ki not in used_known:
            matches.append((score, fi, ki, fb))
            used_findings.add(fi)
            used_known.add(ki)

    # Calculate reward
    total_issue_reward = sum(score for score, _, _, _ in matches)
    correct_count = len(matches)

    # Normalize by number of known issues
    issue_reward = total_issue_reward / num_known

    # False positive penalty: findings that didn't match any known issue
    false_positives = len(findings) - correct_count
    fp_penalty = false_positives * 0.05

    # Coverage bonus: finding all issues
    coverage = correct_count / num_known
    coverage_bonus = 0.1 if coverage >= 1.0 else 0.0

    total_reward = max(0.0, min(1.0, issue_reward - fp_penalty + coverage_bonus))

    # Build feedback
    feedback_lines = []
    feedback_lines.append(f"Found {correct_count}/{num_known} known issues.")
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


# ---------------------------------------------------------------------------
# Environment class
# ---------------------------------------------------------------------------

TASK_ORDER = ["easy", "medium", "hard"]
MAX_STEPS_PER_TASK = 3  # Agent gets up to 3 attempts per task


class CodeReviewEnvironment(Environment):
    """
    Code Review RL Environment.

    The agent reviews code snippets and submits findings. It receives partial
    rewards for correctly identifying bugs, logic errors, and security
    vulnerabilities. The environment presents 3 tasks of increasing difficulty.

    Episode flow:
      1. reset() → presents the first task (easy)
      2. Agent submits findings via step()
      3. Gets feedback and reward; can retry (up to MAX_STEPS_PER_TASK)
      4. After max steps or done, moves to next task
      5. Episode ends after all 3 tasks
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._current_task_idx = 0
        self._steps_this_task = 0
        self._task_scores: Dict[str, float] = {}
        self._best_score_this_task = 0.0
        self._best_correct_this_task = 0
        self._episode_done = False

    def reset(self) -> CodeReviewObservation:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._current_task_idx = 0
        self._steps_this_task = 0
        self._task_scores = {}
        self._best_score_this_task = 0.0
        self._best_correct_this_task = 0
        self._episode_done = False

        task = TASKS[TASK_ORDER[0]]
        return CodeReviewObservation(
            task_id=task["task_id"],
            task_description=task["description"],
            difficulty=task["difficulty"],
            code_to_review=task["code"],
            language=task["language"],
            num_known_issues=len(task["known_issues"]),
            feedback="New episode started. Review the code and submit your findings.",
            issues_found_so_far=0,
            done=False,
            reward=0.0,
        )

    def step(self, action: CodeReviewAction) -> CodeReviewObservation:
        self._state.step_count += 1

        if self._episode_done:
            return CodeReviewObservation(
                task_id="done",
                task_description="Episode is complete.",
                difficulty="",
                code_to_review="",
                language="python",
                num_known_issues=0,
                feedback="Episode already finished. Call reset() to start a new episode.",
                issues_found_so_far=0,
                done=True,
                reward=0.0,
            )

        task_key = TASK_ORDER[self._current_task_idx]
        task = TASKS[task_key]
        self._steps_this_task += 1

        # Grade the submission
        reward, feedback, correct_count = grade_review(action.findings, task_key)

        # Track best score for this task
        if reward > self._best_score_this_task:
            self._best_score_this_task = reward
            self._best_correct_this_task = correct_count

        # Determine if we move to next task
        perfect = correct_count == len(task["known_issues"])
        exhausted_steps = self._steps_this_task >= MAX_STEPS_PER_TASK
        advance = perfect or exhausted_steps

        if advance:
            # Record best score for this task
            self._task_scores[task_key] = self._best_score_this_task

            self._current_task_idx += 1
            self._steps_this_task = 0
            self._best_score_this_task = 0.0
            self._best_correct_this_task = 0

            if self._current_task_idx >= len(TASK_ORDER):
                # Episode complete
                self._episode_done = True
                avg_score = sum(self._task_scores.values()) / len(self._task_scores)
                summary = "; ".join(
                    f"{k}: {v:.2f}" for k, v in self._task_scores.items()
                )
                return CodeReviewObservation(
                    task_id="done",
                    task_description="All tasks complete.",
                    difficulty="",
                    code_to_review="",
                    language="python",
                    num_known_issues=0,
                    feedback=f"Episode complete! Scores — {summary}. Average: {avg_score:.2f}",
                    issues_found_so_far=0,
                    done=True,
                    reward=reward,
                    metadata={"task_scores": self._task_scores, "average": avg_score},
                )
            else:
                # Present next task
                next_key = TASK_ORDER[self._current_task_idx]
                next_task = TASKS[next_key]
                transition_msg = (
                    f"--- Previous task ({task_key}) result ---\n{feedback}\n"
                    f"--- Moving to next task: {next_key} ---\n"
                    f"Review the new code and submit your findings."
                )
                return CodeReviewObservation(
                    task_id=next_task["task_id"],
                    task_description=next_task["description"],
                    difficulty=next_task["difficulty"],
                    code_to_review=next_task["code"],
                    language=next_task["language"],
                    num_known_issues=len(next_task["known_issues"]),
                    feedback=transition_msg,
                    issues_found_so_far=0,
                    done=False,
                    reward=reward,
                )
        else:
            # Same task, another attempt
            remaining = MAX_STEPS_PER_TASK - self._steps_this_task
            retry_msg = (
                f"{feedback}\n"
                f"You have {remaining} attempt(s) remaining for this task. "
                f"Try to find more issues or improve your descriptions."
            )
            return CodeReviewObservation(
                task_id=task["task_id"],
                task_description=task["description"],
                difficulty=task["difficulty"],
                code_to_review=task["code"],
                language=task["language"],
                num_known_issues=len(task["known_issues"]),
                feedback=retry_msg,
                issues_found_so_far=self._best_correct_this_task,
                done=False,
                reward=reward,
            )

    @property
    def state(self) -> State:
        return self._state
