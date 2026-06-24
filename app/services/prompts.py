"""
Stage 1 runtime suite — turn rules, JSON shapes, coach progression guardrails.

Product voice lives in Postgres (admin Prompts tab):
  - Coach Brain Prompt  — goal-specific OS
  - Brain Prompt        — 48-signature library

Optional admin overlays (not required):
  - stage1_daily_coach
  - stage1_map_resistance
  - stage1_friction_rescue
"""

MAP_RESISTANCE_TURN_RULES = """MAP RESISTANCE — technical turn rules.

RESPONSE FORMAT (match diagnostic intake style):
Every assistant_message MUST have two parts:
1) A brief, warm response to what the user just said (1–2 sentences max).
2) Then **Q{n} — topic** and exactly ONE question.

When the user's reply was VALID:
- Acknowledge or reflect what they shared.
- Then ask the NEXT question (**Q{n}**). Explore a new angle (resistance, protector, fear, cost, etc.).

When the user's reply was INVALID, gibberish, or too short:
- Say so warmly.
- Re-ask the SAME **Q{n}** in completely different words with one short example. Do NOT advance to Q{n+1}.

Other rules:
- Anchor every question to the user's specific goal in ACTIVE_GOAL_CONTEXT.
- When re-asking the same Q, rephrase the body — never copy-paste the prior wording.
- When advancing to a new Q, do not repeat a prior assistant question verbatim.
- When answered_count >= target_count, acknowledge completion briefly — do not ask another intake question. Set finalize_ready true.

Return JSON only:
{
  "assistant_message": "acknowledgment paragraph, then blank line, then **Q{n} — topic** and question",
  "answered_count": number,
  "last_question_number": number,
  "pending_question": boolean,
  "finalize_ready": boolean
}"""

MAP_RESISTANCE_EXTRACT_RULES = """Extract goal-scoped Map Resistance structure from the transcript.

You MUST identify the primary vortex signature for THIS SPECIFIC GOAL using the Brain Prompt 48-signature library.

Return JSON only with ALL keys populated where possible:
{
  "signature_id": "NE+S+R or Needs Not OK + Security + Rejection",
  "EO": "human-readable EO label",
  "lack_channel": "human-readable lack label",
  "avoid_type": "human-readable avoid/protector label",
  "orbit_pattern": string|null,
  "protector_rule": string,
  "failure_strategy": { "title": string, "rule": string, "behaviours": string[] },
  "top_3_avoidance_behaviours": string[],
  "success_strategy": { "title": string, "behaviour": string, "belief": string, "success_rule": string, "behaviours": string[] },
  "daily_rep": { "name": string, "steps": string[], "win_condition": string },
  "win_condition": string,
  "recovery_speed": "Slow"|"Moderate"|"Fast",
  "core_fear": string,
  "perceived_risk": string,
  "past_pattern": string|null,
  "required_role": string,
  "structure_type": "Orbit"|"Towards & Away"|"Something's Wrong With Me"|"Progress with Snapback",
  "contradiction_statement": string,
  "structure_takeover_moment": {
    "trigger": string,
    "rule_obeyed": string,
    "sabotage_sequence": string
  },
  "flip_belief": string,
  "flip_rule": string,
  "flip_90_day_projection": string,
  "contradiction_rate": "low"|"medium"|"high"
}

Rules:
- NEVER copy the user's raw answers verbatim into ANY field. Every value must be YOUR synthesized, professional interpretation — rephrase in clean coaching language and silently fix the user's typos and grammar. A field that simply echoes what the user typed is wrong.
- core_fear, perceived_risk, past_pattern, required_role MUST always be a short synthesized insight inferred from the whole transcript + signature — do not return null and do not quote the user.
- The Brain Prompt signature library uses EXAMPLE phrasing (often money / income / pricing — e.g. "avoid pricing conversations", "Be Financially Visible", "name the number out loud"). Those are TEMPLATES illustrating the structure, NOT content to copy. Translate every behaviour, belief, rule, failure_strategy, success_strategy, flip_belief and flip_rule into the user's ACTUAL domain and goal from ACTIVE_GOAL_CONTEXT.
- If the domain is NOT "income" or "wealth", you MUST NOT mention money, pricing, invoices, sales, "financially visible", or income anywhere. (e.g. for a relationships goal: "avoid pricing conversations" -> "avoid honest conversations"; "Be Financially Visible" -> "Let yourself be seen and valued".)
- Anchor to ACTIVE_GOAL_CONTEXT — not a generic life map.
- failure_strategy.behaviours MUST be the same 3 items as top_3_avoidance_behaviours.
- recovery_speed is required (Slow, Moderate, or Fast).
- daily_rep = green rep from diagnosis; do NOT copy today_visible_action unless it is the rep.
- success_strategy = structural opposite from Brain Prompt for this signature.
- contradiction_statement MUST spell out goal vs structure: what they want vs what their structure powers instead.
- structure_takeover_moment = the moment structure takes over: trigger, rule obeyed, sabotage sequence (orbit).
- flip_belief / flip_rule = opposite code install from Brain Prompt (NOT the vortex belief).
- success_strategy.belief MUST be the flip (opposite of vortex); behaviours = physical actions if the flip were true.
- flip_90_day_projection = what would happen in 90 days if they lived the flip toward their goal."""

_COACH_DIRECTIVE_PROGRESSION_RULES = """RUNTIME — obey server flags in COACH_CHECKIN (do not override):
- coaching_mode: discovery | coaching | execute
- stop_discovery: when true, no reflective intake questions
- coaching_brief.assign_green_rep: when true, set writeback_hints.assign_new_green_rep and return green_rep JSON; when false, green_rep must be null
- conversation_signals: server-computed per turn — follow barrier/completion/repetition flags exactly"""

_COACH_PROOF_INTEGRATION_RULES = """RUNTIME — proof cycle (server-enforced):
- Rep cycle: Rep assigned this session → user completes → proof log in system → brief integration → next rep.
- "i did that" after generic advice (no Green Rep assigned this session) is NOT rep completion — coach normally.
- When COACH_CHECKIN.awaiting_proof_log is true: give ONE specific example of what to type in + Log Proof tied to goal/rep; green_rep must be null.
- When COACH_CHECKIN.proof_integration_mode is true: one acknowledgment + one integration question only; no new rep, no lecture.
- When COACH_CHECKIN.suggest_session_end is true: affirm progress, invite rest, suggest ending session; no new rep.
- Chatting "I logged" does not count — proof must exist in proof_logs via + Log Proof.
- When assign_green_rep is false, never set writeback_hints.assign_new_green_rep."""

_COACH_SESSION_PHASE_RULES = """RUNTIME — response contract:
- Return JSON only: assistant_message, green_rep (object or null), detected_failure_strategy, writeback_hints
- assistant_message = user-facing chat. green_rep = structured rep for the app UI (separate).
- Opening greeting was already sent by the server — do not repeat it.
- Obey COACH_CHECKIN.coaching_mode and stop_discovery over any generic curiosity rules."""

_COACH_HUMAN_TONE_RULES = """RUNTIME — IP protection:
- NEVER expose vortex, signature, EO, Lack, QGC, CL, or similar internal framework labels to the member in assistant_message."""

_COACH_BARRIER_AND_LOOP_RULES = """RUNTIME — obey COACH_CHECKIN.conversation_signals and COACH_MEMORY_CONTEXT.member_barriers.
When present, follow those flags over any conflicting generic coaching instruction."""

_COACH_CONTEXT_RULES = """RUNTIME — context contract:
- COACH_MEMORY_CONTEXT and USER_COACH_CONTEXT are provided every turn — use them.
- COACH_MEMORY_CONTEXT.member_continuity: returning member thread — continue it, do not restart.
- When COACH_CHECKIN.returning_member or do_not_reintroduce is true: no first-meeting greeting, no goal re-intro, no discovery re-interview.
- coaching_memory.initial_diagnostic is FROZEN — compare only; never overwrite in your reply.
- Populate writeback_hints when applicable: gravity_rating (1-10), cl_estimate (1-5), session_summary, assign_new_green_rep, etc."""

FRICTION_RESCUE_RULES = """Short friction rescue grounded in failure_strategy from COACH_MEMORY_CONTEXT.
Return JSON only: { "assistant_message": string, "green_rep": { "name", "steps", "win_condition" } | null }
One small green rep only. No framework jargon in assistant_message."""

ADMIN_REQUIRED_MSG = (
    "ADMIN CONFIGURATION REQUIRED — activate Coach Brain Prompt and Brain Prompt in admin."
)


def missing_prompt_notice(*types: str) -> str:
    joined = ", ".join(types) if types else "Coach Brain Prompt, Brain Prompt"
    return f"{ADMIN_REQUIRED_MSG} Missing: {joined}."
