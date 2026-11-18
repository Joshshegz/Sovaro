def approved_brand_memory(brand, limit=50):
    """Return approved brand knowledge as prompt data, never executable instructions."""
    memories = brand.memories.filter(status="confirmed", is_active=True).order_by("category", "-updated_at")[:limit]
    if not memories:
        return "No additional confirmed brand memory has been saved."
    lines = []
    for memory in memories:
        evidence = f" Evidence: {memory.evidence.strip()}" if memory.evidence.strip() else ""
        lines.append(f"- {memory.get_category_display()}: {memory.statement.strip()}{evidence}")
    return "\n".join(lines)
