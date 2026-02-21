"""Narration Generator - Convert reasoning steps into natural, conversational speech."""

from typing import List, Optional

from loguru import logger

from .models import ReasoningStep


# System prompt that defines the narration speaking style
NARRATION_SYSTEM_PROMPT = """You are a friendly, conversational pair programmer narrating your thought process 
while writing code. You speak naturally, like a helpful coworker explaining what they're doing.

Rules:
- Keep narrations SHORT (1-2 sentences, under 150 characters when possible)
- Use conversational tone with occasional filler words ("hmm", "okay", "let me see")
- Vary your phrasing - don't repeat the same patterns
- Reference specific file names and concepts when available
- Match your tone to the thinking type:
  * Planning: thoughtful, considering options
  * Analyzing: curious, investigative
  * Implementing: confident, action-oriented  
  * Debugging: careful, detective-like
  * Testing: methodical, thorough
- NEVER use markdown, code blocks, or formatting - this will be spoken aloud
- NEVER say "I'm an AI" or break character
- Sound natural, not robotic"""

# Tone-specific intro phrases for variety
TONE_INTROS = {
    "planning": [
        "Alright, let me think about this...",
        "Okay, so here's my plan...",
        "Let me figure out the best approach...",
        "Thinking about how to structure this...",
        "So the strategy here is...",
    ],
    "analyzing": [
        "Let me take a look at...",
        "I'm checking out...",
        "Looking at the existing code in...",
        "Let me examine...",
        "Hmm, let me see what's in...",
    ],
    "implementing": [
        "Now I'm writing...",
        "Okay, creating...",
        "Time to implement...",
        "Now for the actual code...",
        "Building out...",
    ],
    "debugging": [
        "Hmm, I see an issue...",
        "Wait, something's not right...",
        "Let me investigate this...",
        "I noticed a problem with...",
        "Okay, need to fix...",
    ],
    "testing": [
        "Let me verify this works...",
        "Running a quick check...",
        "Time to test...",
        "Making sure everything's solid...",
        "Checking the results...",
    ],
}


class NarrationGenerator:
    """
    Generate natural, conversational narration text from reasoning steps.
    
    Uses an LLM for dynamic narration generation with fallback to template-based
    narration when the LLM is unavailable.
    """

    def __init__(self, llm_client=None):
        """
        Initialize with optional LLM client for dynamic narration.
        
        Args:
            llm_client: An async Anthropic client, or None for template-based narration.
        """
        self.llm_client = llm_client
        self.narration_style = "conversational pair programmer"
        self._narration_count = 0
        logger.info(
            f"NarrationGenerator initialized "
            f"({'LLM-powered' if llm_client else 'template-based'})"
        )

    async def generate_narration(
        self,
        step: ReasoningStep,
        previous_steps: Optional[List[ReasoningStep]] = None,
    ) -> str:
        """
        Generate natural narration for a reasoning step.
        
        Args:
            step: The current reasoning step to narrate.
            previous_steps: Previous steps for context continuity.
        
        Returns:
            Narration text to be spoken aloud.
        """
        previous_steps = previous_steps or []
        self._narration_count += 1

        # Try LLM-powered narration first
        if self.llm_client:
            try:
                narration = await self._generate_llm_narration(step, previous_steps)
                if narration:
                    logger.debug(f"LLM narration for step {step.step_number}: {narration[:60]}...")
                    return narration
            except Exception as e:
                logger.warning(f"LLM narration failed, falling back to template: {e}")

        # Fallback to template-based narration
        narration = self._generate_template_narration(step, previous_steps)
        logger.debug(f"Template narration for step {step.step_number}: {narration[:60]}...")
        return narration

    async def _generate_llm_narration(
        self,
        step: ReasoningStep,
        previous_steps: List[ReasoningStep],
    ) -> Optional[str]:
        """Generate narration using LLM."""
        prompt = self.get_narration_prompt(step, previous_steps)

        response = await self.llm_client.messages.create(
            model="claude-sonnet-4-6",
            system=NARRATION_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt},
            ],
            max_tokens=100,
            temperature=0.8,
        )

        narration = response.content[0].text if response.content else None
        if narration:
            return narration.strip().strip('"').strip("'")
        return None

    def get_narration_prompt(
        self,
        step: ReasoningStep,
        previous_steps: List[ReasoningStep],
    ) -> str:
        """Build the prompt for LLM narration generation."""
        # Context from previous steps
        context_lines = []
        if previous_steps:
            context_lines.append("Recent steps:")
            for ps in previous_steps[-3:]:
                context_lines.append(f"  - Step {ps.step_number} ({ps.thinking_type}): {ps.step_description}")

        context_str = "\n".join(context_lines) if context_lines else "This is the first step."

        files_str = ", ".join(step.files_involved) if step.files_involved else "no specific files"

        return f"""Generate a short, natural narration for this coding step. 
Speak as if you're a pair programmer explaining what you're doing RIGHT NOW.

Current step:
- Step {step.step_number}: {step.step_description}
- Type: {step.thinking_type}
- Files: {files_str}

{context_str}

Narrate this step in 1-2 casual sentences (spoken aloud, no formatting):"""

    def _generate_template_narration(
        self,
        step: ReasoningStep,
        previous_steps: List[ReasoningStep],
    ) -> str:
        """Generate narration using templates (fallback when LLM unavailable)."""
        thinking_type = step.thinking_type
        description = step.step_description
        files = step.files_involved

        # Pick an intro phrase (rotate through options)
        intros = TONE_INTROS.get(thinking_type, TONE_INTROS["analyzing"])
        intro = intros[self._narration_count % len(intros)]

        # Build the narration based on thinking type
        if thinking_type == "planning":
            if files:
                narration = f"{intro} We'll need to work with {', '.join(files[:2])}. {description}"
            else:
                narration = f"{intro} {description}"

        elif thinking_type == "analyzing":
            if files:
                narration = f"{intro} {files[0]}. {description}"
            else:
                narration = f"{intro} {description}"

        elif thinking_type == "implementing":
            if files:
                narration = f"{intro} {files[0]}. {description}"
            else:
                narration = f"{intro} {description}"

        elif thinking_type == "debugging":
            narration = f"{intro} {description}"

        elif thinking_type == "testing":
            narration = f"{intro} {description}"

        else:
            narration = f"{intro} {description}"

        # Ensure it's not too long for speech
        if len(narration) > 250:
            narration = narration[:247] + "..."

        return narration

    @property
    def narration_count(self) -> int:
        """Number of narrations generated."""
        return self._narration_count
