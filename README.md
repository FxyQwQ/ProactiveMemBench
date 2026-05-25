# ProactiveMemBench

**ProactiveMemBench** is a benchmark for evaluating the *proactive memory association* capability of large language models in long-term conversational settings.

## What is Proactive Memory Association?

When a user mentions concept A in the current turn, the model should — based on memorized multi-session conversation history — proactively recall related concepts B, C, D that the user is *not* currently mentioning but has previously shared.

**Example:**
> - User says: "I heard a Debussy piece on the radio this morning."
> - Model should proactively recall (from conversation history):
>   - The user is currently practicing Debussy's *Clair de Lune* (mentioned in Session 3)
>   - Teacher Zhang commented on the user's tonal quality (mentioned in Session 7)
>   - The user practices piano every Wednesday and Friday (mentioned in Session 1)

## Benchmark Statistics

| Dimension | Per Domain | Total (5 domains) |
|-----------|-----------|-------------------|
| Topic domains | — | 5 (music, cooking, fitness, pet, travel) |
| User personas | 1 | 5 |
| Memory units | 60 | 300 |
| Association pairs | 200 | 1,000 |
| Dialogue sessions | 20 | 100 |
| Turns per session | 20 | — |
| Total dialogue turns | 400 | 2,000 |
| Evaluation questions | 100 | 504 |
| Candidates per question | 3 (ground truth) | — |

## Five Types of Memory Association

| Type | Definition | Example |
|------|-----------|---------|
| **Temporal** | Recall time-bound activity patterns | "Monday evening" → piano practice → Hanon warm-up |
| **Entity** | Recall entity-linked associations | Mention Beethoven → grandmother loves Moonlight Sonata |
| **Emotional** | Recall emotion↔behavior mappings | Feeling stressed → plays Bach WTC to relax |
| **Behavioral Pattern** | Recall habitual co-occurrences | Before practicing → brews green tea + study room |
| **Multi-hop** | Recall via ≥2 reasoning hops | Debussy → Clair de Lune → Teacher Zhang → tonal feedback |

## Data Structure

```
ProactiveMemBench/
├── README.md
├── LICENSE
└── data/
    ├── music/              # Music domain
    ├── cooking/            # Cooking domain
    ├── fitness/            # Fitness domain
    ├── pet/                # Pet care domain
    └── travel/             # Travel domain
```

Each domain directory contains:

| File | Description |
|------|-------------|
| `step0_persona.json` | User persona (global constraint for all generations) |
| `step1_concept_pairs.json` | 60 memory units (5 types × 12) |
| `step2_associations.json` | 200 pairwise association scores (4 dimensions) |
| `step3_session_groups.json` | Session grouping plan (20 sessions × 3 units) |
| `step4_conversations.json` | 20 sessions × 20 turns of dialogue |
| `step5_proactive_questions.json` | 100 evaluation questions with ground-truth candidates |

## Data Format

### Evaluation Question (`step5_proactive_questions.json`)

```json
{
  "id": "q_001",
  "trigger_type": "temporal",
  "question": "It's Wednesday evening at 8pm, time to head to the study.",
  "trigger_concept": "Wednesday evening 8pm",
  "candidate_set": [
    {"concept": "Hanon finger exercises", "reason": "Wednesday evening → fixed practice → warm-up is Hanon"},
    {"concept": "Debussy Clair de Lune", "reason": "Wednesday evening → fixed practice → current main piece"},
    {"concept": "Professor Zhang", "reason": "Practice Clair de Lune → tonal issues → Professor Zhang's feedback"}
  ],
  "difficulty": "medium",
  "source_pairs": ["time_03"],
  "reasoning": "User only mentions time and place; model must recall the behavioral pattern and related people for that time slot."
}
```

### Dialogue Session (`step4_conversations.json`)

```json
{
  "session_id": 1,
  "turns": [
    {
      "turn_id": 1,
      "role": "user",
      "content": "...",
      "timestamp": "2026-03-01T20:15:00",
      "planted_units": ["time_01"],
      "mentioned_entities": ["Bach", "Monday"]
    }
  ],
  "unit_coverage": {
    "time_01": {"planted": true, "turns": [1, 3]}
  }
}
```

## Evaluation Protocol

```
Input:  All 20 sessions of conversation history + 1 proactive question (trigger utterance)
         ↓
Model:  Generate a response based on memorized conversation history
         ↓
Metric: Does the response proactively mention concepts from the candidate_set?
```

### Metrics

| Metric | Definition |
|--------|-----------|
| **Recall@k** | Fraction of 3 ground-truth candidates mentioned in k response turns |
| **Precision** | Fraction of proactively mentioned concepts that are in the ground truth |
| **By-type Recall** | Recall broken down by the 5 association types |
| **By-difficulty Recall** | Recall broken down by easy / medium / hard |

## Difficulty Levels

| Level | Count per type | Definition |
|-------|---------------|-----------|
| Easy | 6 | Single-hop direct association |
| Medium | 8 | Requires synthesizing 2 memory units |
| Hard | 6 | Cross-session multi-hop reasoning |

## Construction Pipeline

The benchmark is constructed via a 6-step LLM-driven pipeline:

1. **Persona Generation** — Create a detailed user persona per domain
2. **Memory Unit Generation** — Generate 60 memory units (5 types × 12), sequentially to avoid contradictions
3. **Association Scoring** — Evaluate 200 sampled pairs across 4 dimensions
4. **Session Grouping** — Assign memory units to 20 sessions; high-association pairs deliberately split across sessions
5. **Dialogue Generation** — Generate 20-turn conversations with planted memory units
6. **Question Generation** — Create 100 evaluation questions with ground-truth candidate sets (top-3)

## Quality Assurance

### Human Validation

To verify the quality of the automatically constructed benchmark, we conduct a human spot-check on a random sample of 125 test instances (25 per topic domain). Two annotators independently evaluate each instance along three criteria:

1. **Query validity** — whether the trigger utterance is natural and contains only the intended trigger memory unit without leaking candidate information
2. **Candidate correctness** — whether each candidate in the ground-truth set is genuinely inferable from the conversation history and absent from the query
3. **Evidence support** — whether the cited source memory units fully support the association path described in the reasoning field

An instance is marked as *accepted* if it passes all three criteria.

| Criterion | Pass Rate |
|-----------|-----------|
| Query validity | 100% |
| Candidate correctness | 98.4% |
| Evidence support | 98.4% |
| **Overall acceptance** | **98.4%** |

The remaining invalid cases are primarily evidence-support errors, where the quoted evidence is related to the reference answer but does not fully support all required claims. We attribute this to the multi-hop nature of hard-difficulty instances, where the LLM-generated reasoning occasionally omits an intermediate link. Based on these findings, we manually corrected the rejected instances and incorporated the revised versions into the final benchmark.

### LLM-based Completeness Verification

Since each test instance only retains the top-3 most relevant memory units as its ground-truth candidate set, a natural concern is whether important candidates are omitted. To verify completeness, we employ three strong LLMs (GPT-4o, Claude-3.5-Sonnet, and Gemini-1.5-Pro) as independent judges. For each test instance, we provide the full conversation history and the trigger utterance, and ask each model to list all memory units it deems worth proactively surfacing, ranked by relevance. We then compare each model's top-3 selections against our ground-truth candidate set.

A candidate is flagged as a potential omission if at least two out of three judges rank it within their top-3 but it is absent from our annotations. Results show that across all 504 instances, the three judges reach **majority agreement with our ground-truth candidate set on 96% of instances** (i.e., at least 2 of 3 candidates overlap). For the remaining 4%, manual inspection reveals that the divergence stems from equally plausible alternative associations rather than clear omissions — confirming that our top-3 selection is well-calibrated and the ground-truth candidate sets are reliable.

## License

This dataset is released under the [MIT License](LICENSE).
