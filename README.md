# Code Review Environment

An OpenEnv reinforcement learning environment where AI agents learn to review Python code for bugs, logic errors, and security vulnerabilities.

## Motivation

Code review is one of the most time-consuming tasks in software engineering. Training AI agents to perform thorough, accurate code reviews would directly improve developer productivity. This environment provides a structured training ground with realistic code snippets containing real-world bugs that professional developers encounter daily.

Unlike toy environments, the skills trained here map directly to production use cases: static analysis tools, CI/CD review bots, and developer copilots.

## Environment Description

The agent receives a Python code snippet and must identify issues by specifying:
- **Line number** of the issue
- **Issue type** (bug, logic_error, or security_vulnerability)
- **Description** of what's wrong
- **Suggested fix**

The environment grades each finding against known ground-truth issues using a deterministic grading system.

## Action Space

```python
class CodeReviewAction(Action):
    findings: List[ReviewFinding]  # List of identified issues
    review_summary: str            # Overall assessment

class ReviewFinding(Action):
    line_number: int       # Where the issue is
    issue_type: str        # bug | logic_error | security_vulnerability
    description: str       # What's wrong
    suggested_fix: str     # How to fix it
```

## Observation Space

```python
class CodeReviewObservation(Observation):
    task_id: str              # Current task identifier
    task_description: str     # What to look for
    difficulty: str           # easy | medium | hard
    code_to_review: str       # The code snippet
    language: str             # Programming language
    num_known_issues: int     # Number of issues to find
    feedback: str             # Grading feedback from previous attempt
    issues_found_so_far: int  # Correct issues found
```

## Tasks

| Task | Difficulty | Issues | Description |
|------|-----------|--------|-------------|
| easy_bugs | Easy | 4 | Undefined variables, off-by-one errors, missing returns, division by zero |
| medium_logic | Medium | 4 | Incorrect algorithm (duplicate detection), missing merge logic, undefined discount |
| hard_security | Hard | 6 | SQL injection, XSS, path traversal, command injection, insecure deserialization, hardcoded secrets |

### Difficulty Progression
- **Easy**: Bugs that would be caught by a linter or basic testing
- **Medium**: Logic errors requiring understanding of algorithm correctness
- **Hard**: Security vulnerabilities requiring knowledge of OWASP Top 10

## Reward Design

Rewards are computed deterministically against ground-truth issues and are continuous between 0.0 and 1.0, with rich partial credit:

- **Line accuracy** (0.0-0.3): Exact line match = 0.3, within ±3 lines = proportional credit
- **Description quality** (0.0-0.5): Keyword matching against ground truth descriptions
- **Issue type** (+0.1): Correct classification of the issue category
- **Suggested fix** (+0.1): Providing an actionable fix suggestion
- **Coverage bonus** (+0.1): Finding ALL issues in a task
- **False positive penalty** (-0.05 each): Penalizes flagging correct code as buggy

The agent gets up to 3 attempts per task, with the best-performing attempt determining the task score.

## Why This Environment Matters

This is not a toy environment. It simulates real-world software engineering tasks:

- Static code analysis
- Security auditing (OWASP-style vulnerabilities)
- Debugging production logic errors

The reward signal reflects real developer expectations:
accuracy, correctness, and actionable fixes.

This makes it suitable for training agents used in:
- CI/CD pipelines
- Developer copilots
- Automated code review systems

## Multi-Step Learning

The environment supports iterative refinement:

- Agents receive feedback after each attempt
- They can improve findings across steps
- Rewards accumulate over multiple interactions

This encourages learning strategies beyond single-shot prediction.

## Evaluation Protocol

Each episode consists of sequential tasks (easy → medium → hard).

- The agent receives code and must identify all issues
- Up to 3 attempts per task
- The environment returns partial rewards after each step
- Final score is the average reward across all steps

The inference script logs:
- [START] episode metadata
- [STEP] per-action reward and status
- [END] final score and success flag

This environment fully complies with the OpenEnv specification and supports both local Docker execution and remote evaluation via Hugging Face Spaces.

## Setup

```bash
# Install dependencies
pip install openenv-core

# Initialize and build
cd code_review_env
uv sync

# Build Docker image
docker build -t code_review_env -f Dockerfile .

# Run
docker run -p 8000:8000 code_review_env
```

## Usage

```python
from openenv.core.env_client import EnvClient

client = EnvClient.from_docker_image("code_review_env")
obs = client.reset()
print(obs["code_to_review"])

# Submit findings
action = {
    "findings": [
        {
            "line_number": 6,
            "issue_type": "bug",
            "description": "Off-by-one: loop starts at 1, skipping first record",
            "suggested_fix": "Change range(1, len(records)) to range(len(records))"
        }
    ],
    "review_summary": "Found indexing error in loop"
}
obs = client.step(action)
print(obs["feedback"])
print(obs["reward"])
```

## Baseline Scores

Run the inference script:
```bash
# Set environment variables
export HF_TOKEN=your_token
export LOCAL_IMAGE_NAME=code_review_env

# Run baseline
uv run inference.py
```

Baseline performance (Qwen2.5-72B-Instruct):
- Easy task: ~0.7-0.9
- Medium task: ~0.5-0.7
- Hard task: ~0.4-0.6
- Average: ~0.5-0.7

## Deployment

```bash
openenv push your-hf-username/code_review_env
```

## License

BSD-style license. See LICENSE file.
