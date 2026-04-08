"""
Data models for the Code Review Environment.

An RL environment where an AI agent reviews code for bugs, logic errors,
and security vulnerabilities, receiving partial rewards for correct findings.
"""

from typing import List

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class ReviewFinding(Action):
    """A single issue found during code review."""
    line_number: int = Field(..., description="Line number where the issue exists")
    issue_type: str = Field(
        ...,
        description="Type of issue: 'bug', 'logic_error', or 'security_vulnerability'",
    )
    description: str = Field(..., description="Description of the issue found")
    suggested_fix: str = Field(default="", description="Suggested code fix")


class CodeReviewAction(Action):
    """Action for the Code Review environment - submit review findings."""
    findings: List[ReviewFinding] = Field(
        default_factory=list,
        description="List of issues found in the code. Submit empty list if no issues found.",
    )
    review_summary: str = Field(
        default="", description="Overall summary of the code review"
    )


class CodeReviewObservation(Observation):
    """Observation from the Code Review environment."""
    task_id: str = Field(default="", description="Current task identifier")
    task_description: str = Field(default="", description="What to look for in this review")
    difficulty: str = Field(default="", description="easy, medium, or hard")
    code_to_review: str = Field(default="", description="The code snippet to review")
    language: str = Field(default="python", description="Programming language of the code")
    num_known_issues: int = Field(default=0, description="Number of issues to find")
    feedback: str = Field(default="", description="Feedback on your previous review attempt")
    issues_found_so_far: int = Field(default=0, description="Correct issues identified so far")
