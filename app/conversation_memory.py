
from typing import Optional


# Per-user conversation state, keyed by Teams user_id
conversation_memory: dict = {}

MAX_HISTORY_TURNS = 2   # keep last 2 user+assistant pairs = 4 entries


def get_history(memory: dict) -> list[dict]:
    return memory.get("history", [])


def get_formatted_history(user_id: str) -> str:
    """
    Render structured turns into a clean string for the ORCHESTRATION_PROMPT.
    Includes data_snapshot values inline so the LLM can reference them.
    """
    memory = conversation_memory.get(user_id, {})
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
    user_id: str,
    question: str,
    response: str,
    data_snapshot: Optional[dict] = None,
) -> None:
    """
    Save one user+assistant turn to memory.
    data_snapshot should contain the calculated IC values for this response.
    """
    if user_id not in conversation_memory:
        conversation_memory[user_id] = {"history": []}
    
    memory = conversation_memory[user_id]

    memory["history"].append({"role": "user", "content": question})

    assistant_turn = {"role": "assistant", "content": response}
    if data_snapshot:
        assistant_turn["data_snapshot"] = data_snapshot

    memory["history"].append(assistant_turn)

    # Trim to last MAX_HISTORY_TURNS pairs
    max_entries = MAX_HISTORY_TURNS * 2
    memory["history"] = memory["history"][-max_entries:]