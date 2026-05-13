"""
Conversation memory for the IC chatbot.

Each user gets a dict keyed by user_id:
{
    "history": [
        {"role": "user",      "content": "what my payout"},
        {"role": "assistant", "content": "Your total IC payout is $10,490.",
                              "data_snapshot": {"total_ic": 10490, "ic_earnings": 10000, ...}},
        ...
    ]
}

The data_snapshot on assistant turns lets the LLM explain "these numbers"
on follow-ups using the exact grounded values — not its own narrative.
"""

from typing import Optional


# Per-user conversation state, keyed by Teams user_id
conversation_memory: dict = {}

MAX_HISTORY_TURNS = 2   # keep last 2 user+assistant pairs = 4 entries


def get_history(memory: dict) -> list[dict]:
    """Return structured turn history for a user."""
    return memory.get("history", [])


def format_history_for_prompt(memory: dict) -> str:
    """
    Render structured turns into a clean string for the ORCHESTRATION_PROMPT.
    Includes data_snapshot values inline so the LLM can reference them.
    """
    history = get_history(memory)
    if not history:
        return "No prior conversation."

    lines = []
    for turn in history:
        role = turn["role"].capitalize()
        content = turn["content"]
        lines.append(f"{role}: {content}")

        # Attach snapshot so LLM can resolve references like "these numbers"
        snapshot = turn.get("data_snapshot")
        if snapshot:
            snapshot_lines = [f"  [{k}: {v}]" for k, v in snapshot.items()]
            lines.append("  [Data available from this response:]")
            lines.extend(snapshot_lines)

    return "\n".join(lines)


def save_turn(
    memory: dict,
    question: str,
    response: str,
    data_snapshot: Optional[dict] = None,
) -> None:
    """
    Save one user+assistant turn to memory.
    data_snapshot should contain the calculated IC values for this response.
    """
    if "history" not in memory:
        memory["history"] = []

    memory["history"].append({"role": "user", "content": question})

    assistant_turn = {"role": "assistant", "content": response}
    if data_snapshot:
        assistant_turn["data_snapshot"] = data_snapshot

    memory["history"].append(assistant_turn)

    # Trim to last MAX_HISTORY_TURNS pairs
    max_entries = MAX_HISTORY_TURNS * 2
    memory["history"] = memory["history"][-max_entries:]