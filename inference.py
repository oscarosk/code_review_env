"""
Inference Script for Code Review Environment
=============================================
MANDATORY:
- API_BASE_URL, MODEL_NAME, HF_TOKEN must be set.
- Uses OpenAI Client for all LLM calls.
- Emits [START], [STEP], [END] stdout format.
"""

import json
import os
import sys
import textwrap

try:
    from openai import OpenAI
except ImportError:
    print("[START] task=setup env=code_review_env model=unknown")
    print("[STEP] step=0 action=import reward=0.00 done=true error=openai_not_installed")
    print("[END] success=false steps=0 score=0.00 rewards=")
    sys.exit(0)

try:
    from models import CodeReviewAction, CodeReviewObservation, ReviewFinding
    from server.code_review_env_environment import CodeReviewEnvironment, TASK_ORDER
except ImportError:
    try:
        sys.path.insert(0, os.getcwd())
        from models import CodeReviewAction, CodeReviewObservation, ReviewFinding
        from server.code_review_env_environment import CodeReviewEnvironment, TASK_ORDER
    except ImportError as e:
        print("[START] task=setup env=code_review_env model=unknown")
        print(f"[STEP] step=0 action=import reward=0.00 done=true error={e}")
        print("[END] success=false steps=0 score=0.00 rewards=")
        sys.exit(0)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
IMAGE_NAME = os.getenv("IMAGE_NAME", "code_review_env")
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME", IMAGE_NAME)
BENCHMARK = "code_review_env"
TEMPERATURE = 0.2

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = textwrap.dedent("""\
You are an expert code reviewer. You will be given code to review and must identify bugs, logic errors, or security vulnerabilities.

IMPORTANT: You must respond ONLY with valid JSON matching this exact schema:
{
  "findings": [
    {
      "line_number": <int>,
      "issue_type": "<bug|logic_error|security_vulnerability>",
      "description": "<clear description of the issue>",
      "suggested_fix": "<how to fix it>"
    }
  ],
  "review_summary": "<brief overall assessment>"
}

Rules:
- Report EVERY issue you can find — the code has a known number of issues
- Be precise about line numbers (count from line 1)
- issue_type must be exactly one of: bug, logic_error, security_vulnerability
- Always provide a suggested_fix with at least 10 characters
- Output ONLY the JSON, no markdown fences, no backticks, no explanation before or after
""")


def build_user_prompt(obs: CodeReviewObservation) -> str:
    parts = [
        f"Task: {obs.task_description}",
        f"Difficulty: {obs.difficulty}",
        f"Number of issues to find: {obs.num_known_issues}",
    ]
    if obs.feedback and "Review the code" not in obs.feedback:
        parts.append(f"\nFeedback from previous attempt:\n{obs.feedback}")
    parts.append(
        f"\nCode to review ({obs.language}):\n```\n{obs.code_to_review}\n```"
    )
    parts.append(f"\nFind exactly {obs.num_known_issues} issues. Respond with ONLY valid JSON.")
    return "\n".join(parts)


def parse_llm_response(text: str) -> CodeReviewAction:
    if not isinstance(text, str) or not text.strip():
        return CodeReviewAction(findings=[], review_summary="Empty response")

    cleaned = text.strip()
    # Strip markdown fences
    if "```" in cleaned:
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                return CodeReviewAction(findings=[], review_summary="Parse failed")
        else:
            return CodeReviewAction(findings=[], review_summary="Parse failed")

    findings = []
    for f in data.get("findings", []):
        try:
            findings.append(ReviewFinding(
                line_number=int(f.get("line_number", 0)),
                issue_type=str(f.get("issue_type", "bug")),
                description=str(f.get("description", "")),
                suggested_fix=str(f.get("suggested_fix", "")),
            ))
        except Exception:
            continue

    return CodeReviewAction(
        findings=findings,
        review_summary=str(data.get("review_summary", "")),
    )


def run_task(client: OpenAI, task_name: str) -> float:
    """Run one task (one episode): reset → LLM review → step → score."""

    # Set the task via env var and create environment
    os.environ["CURRENT_TASK"] = task_name
    env = CodeReviewEnvironment()
    obs = env.reset()

    print(f"[START] task={task_name} env={BENCHMARK} model={MODEL_NAME}")

    step_num = 0
    rewards = []

    # Build prompt from observation
    user_msg = build_user_prompt(obs)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    # Call LLM
    last_error = None
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=2000,
        )
        llm_text = response.choices[0].message.content or ""
    except Exception as e:
        last_error = str(e).replace("\n", " ")[:200]
        llm_text = '{"findings": [], "review_summary": "LLM error"}'

    # Parse into action
    action = parse_llm_response(llm_text)

    # Step environment
    try:
        obs = env.step(action)
        reward = float(obs.reward)
        done = bool(obs.done)
    except Exception as e:
        last_error = str(e).replace("\n", " ")[:200]
        reward = 0.0
        done = True

    step_num += 1
    rewards.append(reward)

    n_findings = len(action.findings)
    error_str = last_error if last_error else "null"
    print(
        f"[STEP] step={step_num} action=review({n_findings}_findings) "
        f"reward={reward:.2f} done={'true' if done else 'false'} "
        f"error={error_str}"
    )

    # Score
    score = max(0.0, min(1.0, reward))
    success = score >= 0.3
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)

    print(
        f"[END] success={'true' if success else 'false'} steps={step_num} "
        f"score={score:.2f} rewards={rewards_str}"
    )
    return score


def main():
    try:
        if not HF_TOKEN:
            print(f"[START] task=setup env={BENCHMARK} model={MODEL_NAME}")
            print("[STEP] step=0 action=check_token reward=0.00 done=true error=HF_TOKEN_not_set")
            print("[END] success=false steps=0 score=0.00 rewards=")
            return

        client = OpenAI(api_key=HF_TOKEN, base_url=API_BASE_URL)

        scores = {}
        for task_name in TASK_ORDER:
            scores[task_name] = run_task(client, task_name)

        avg = sum(scores.values()) / len(scores)
        print(f"\n=== Summary ===")
        for t, s in scores.items():
            print(f"  {t}: {s:.2f}")
        print(f"  Average: {avg:.2f}")

    except Exception as e:
        err = str(e).replace("\n", " ")[:300]
        print(f"[START] task=setup env={BENCHMARK} model={MODEL_NAME}")
        print(f"[STEP] step=0 action=main reward=0.00 done=true error={err}")
        print("[END] success=false steps=0 score=0.00 rewards=")


if __name__ == "__main__":
    main()