# SDD Parser is a dedicated graph node, not part of the PMO Agent

The PMO Agent must only ever receive a structured `SDD` Pydantic model — it never sees raw Markdown. Parsing is the first node in the graph, and the PMO is the second. We considered co-locating parsing inside the PMO to reduce the number of LLM calls, but that would force the PMO to reason about document format alongside orchestration logic, making both harder to test and maintain. Isolating parsing also lets us swap the parser's model or prompt independently of the PMO's.
