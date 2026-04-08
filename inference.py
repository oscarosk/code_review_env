"""
Inference Script for Code Review Environment
=============================================
MANDATORY:
- API_BASE_URL, MODEL_NAME, HF_TOKEN must be set.
- Uses OpenAI Client for all LLM calls.
- Emits [START], [STEP], [END] stdout format.
"""

import asyncio
import json
import os
import textwrap

from openai import OpenAI

# ---------------------------------------------------------------------------
# Environment imports
# ---------------------------------------------------------------------------
from models import CodeReviewAction, ReviewFinding


LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME", "code_review_env")
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")
BENCHMARK = "code_review_env"
MAX_STEPS = 6
TEMPERATURE = 0.2

TASK_ORDER = ["easy", "medium", "hard"]

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
- Report EVERY issue you can find
- Be specific about line numbers
- issue_type must be one of: bug, logic_error, security_vulnerability
- Always provide a suggested_fix
- Output ONLY the JSON, no markdown, no backticks, no explanation
""")


def build_user_prompt(obs: dict) -> str:
    parts = []
    parts.append(f"Task: {obs.get('task_description', '')}")
    parts.append(f"Difficulty: {obs.get('difficulty', '')}")
    parts.append(f"Number of issues to find: {obs.get('num_known_issues', 0)}")
    if obs.get("feedback"):
        parts.append(f"\nFeedback from previous attempt:\n{obs['feedback']}")
    parts.append(f"\nCode to review ({obs.get('language', 'python')}):\n```\n{obs.get('code_to_review', '')}\n```")
    parts.append("\nRespond with ONLY the JSON object containing your findings.")
    return "\n".join(parts)


def parse_llm_response(text: str) -> CodeReviewAction:
    """Parse LLM JSON response into CodeReviewAction."""
    if not isinstance(text, str):
        return CodeReviewAction(findings=[], review_summary="Invalid non-string response")

    # Strip markdown fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                return CodeReviewAction(findings=[], review_summary="Failed to parse response")
        else:
            return CodeReviewAction(findings=[], review_summary="Failed to parse response")

    findings = []
    for f in data.get("findings", []):
        try:
            findings.append(ReviewFinding(
                line_number=int(f.get("line_number", 0)),
                issue_type=f.get("issue_type", "bug"),
                description=f.get("description", ""),
                suggested_fix=f.get("suggested_fix", ""),
            ))
        except Exception:
            continue

    return CodeReviewAction(
        findings=findings,
        review_summary=data.get("review_summary", ""),
    )


async def run_episode(client: OpenAI, env_client):
    """Run a single episode across all tasks."""
    # Reset environment
    reset_result = await env_client.reset()
    obs = reset_result.observation.model_dump()

    step_num = 0
    rewards = []
    last_reward = 0.0
    done = False
    last_error = None
    conversation = [{"role": "system", "content": SYSTEM_PROMPT}]

    task_idx = 0
    current_task = TASK_ORDER[task_idx] if task_idx < len(TASK_ORDER) else "done"

    print(f"[START] task={current_task} env={BENCHMARK} model={MODEL_NAME}")

    while not done and step_num < MAX_STEPS:
        # Build prompt
        user_msg = build_user_prompt(obs)
        conversation.append({"role": "user", "content": user_msg})

        # Call LLM
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=conversation,
                temperature=TEMPERATURE,
                max_tokens=600,
            )
            llm_text = response.choices[0].message.content or '{"findings": [], "review_summary": "Empty response"}'
            conversation.append({"role": "assistant", "content": llm_text})
            conversation = [conversation[0], conversation[-2], conversation[-1]]
        except Exception as e:
            last_error = str(e)
            llm_text = '{"findings": [], "review_summary": "Error"}'

        # Parse response into action
        action = parse_llm_response(llm_text)

        # Step environment
        try:
            step_result = await env_client.step(action)
            obs = step_result.observation.model_dump()
            last_reward = float(step_result.reward)
            done = bool(step_result.done)
            last_error = None
        except Exception as e:
            last_error = str(e)
            last_reward = 0.0
            done = True

        step_num += 1
        rewards.append(last_reward)

        # Detect task transition
        new_task_id = obs.get("task_id", "")
        if new_task_id == "done":
            current_task = "all_tasks"
        elif "medium" in new_task_id and current_task == "easy":
            current_task = "medium"
        elif "hard" in new_task_id and current_task in ("easy", "medium"):
            current_task = "hard"

        action_str = f"review({len(action.findings)}_findings)"
        error_str = last_error if last_error else "null"
        print(
            f"[STEP] step={step_num} action={action_str} "
            f"reward={last_reward:.2f} done={'true' if done else 'false'} "
            f"error={error_str}"
        )

    # Compute final score
    score = sum(rewards) / len(rewards) if rewards else 0.0
    score = min(1.0, max(0.0, score))
    success = score >= 0.3
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)

    print(
        f"[END] success={'true' if success else 'false'} steps={step_num} "
        f"score={score:.2f} rewards={rewards_str}"
    )
    return score


async def amain():
    env_client = None

    try:
        if not HF_TOKEN:
            print("[START] task=setup env=code_review_env model=" + MODEL_NAME)
            print("[STEP] step=0 action=check_env reward=0.00 done=true error=Missing HF_TOKEN environment variable")
            print("[END] success=false steps=0 score=0.00 rewards=")
            return

        client = OpenAI(api_key=HF_TOKEN, base_url=API_BASE_URL)

        from client import CodeReviewEnv

        try:
            env_client = await CodeReviewEnv.from_docker_image(LOCAL_IMAGE_NAME)
        except Exception as e:
            print("[START] task=env_startup env=code_review_env model=" + MODEL_NAME)
            print(f"[STEP] step=0 action=start_env reward=0.00 done=true error={str(e)}")
            print("[END] success=false steps=0 score=0.00 rewards=")
            return

        try:
            score = await run_episode(client, env_client)
            print(f"\nFinal score: {score:.2f}")
        except Exception as e:
            print(f"[STEP] step=0 action=run_episode reward=0.00 done=true error={str(e)}")
            print("[END] success=false steps=0 score=0.00 rewards=")

    finally:
        if env_client is not None:
            try:
                await env_client.close()
            except Exception:
                pass


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()