# Use langgraph to build a COT "model".
# This model is supposed to be transparent for upper layers,
# it receives a HumanMessage and returns an AIMessage.

from dataclasses import dataclass
from typing import Any, List, Optional, Annotated
import time
import json
import logging

from langchain_core.messages import HumanMessage, AIMessage, AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from seedgen2.agent.presets import SeedGen2GenerativeModel


class CoTPrompts:
    PROMPT_COT = """
You are an expert AI assistant that explains your reasoning step by step. For each step, provide a title that describes what you're doing in that step, along with the content. Decide if you need another step or if you're ready to give the final answer. Respond in JSON format with 'title', 'content', and 'next_action' (either 'continue' or 'final_answer') keys. USE AS MANY REASONING STEPS AS POSSIBLE. AT LEAST 3. BE AWARE OF YOUR LIMITATIONS AS AN LLM AND WHAT YOU CAN AND CANNOT DO. IN YOUR REASONING, INCLUDE EXPLORATION OF ALTERNATIVE ANSWERS. CONSIDER YOU MAY BE WRONG, AND IF YOU ARE WRONG IN YOUR REASONING, WHERE IT WOULD BE. FULLY TEST ALL OTHER POSSIBILITIES. YOU CAN BE WRONG. WHEN YOU SAY YOU ARE RE-EXAMINING, ACTUALLY RE-EXAMINE, AND USE ANOTHER APPROACH TO DO SO. DO NOT JUST SAY YOU ARE RE-EXAMINING. USE AT LEAST 3 METHODS TO DERIVE THE ANSWER. USE BEST PRACTICES.

Example of a valid JSON response:
```json
{
    "title": "Identifying Key Information",
    "content": "To begin solving this problem, we need to carefully examine the given information and identify the crucial elements that will guide our solution process. This involves...",
    "next_action": "continue"
}```
"""

    FINAL_PROMPT = "Please provide the final answer based solely on your reasoning above. Do not use JSON formatting. Only provide the text response without any titles or preambles. Retain any formatting as instructed by the original prompt, such as exact formatting for free response or multiple choice."


@dataclass
class COTState:
    """State management for Chain-of-Thought reasoning."""
    model: Any
    messages: Annotated[List[AnyMessage], add_messages]
    error_happened: bool = False
    error_message: str = ""
    step_count: int = 0
    max_steps: int = 25
    final_answer: Optional[str] = None
    next_action: str = "continue"


class GenerateStepNode:
    """Generates a reasoning step."""

    def __call__(self, state: COTState):
        logging.info(f"Generating reasoning step {state.step_count + 1}")
        model = state.model
        messages = state.messages

        # Generate the next reasoning step
        response = model.invoke(messages)
        state.step_count += 1
        state.messages.append(response)

        # Parse the assistant's response
        try:
            step_data = json.loads(response.content)
            state.next_action = step_data.get("next_action", "final_answer")
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON response: {e}")
            state.error_happened = True
            state.error_message = f"Failed to parse JSON response: {e}"
            state.next_action = "final_answer"

        return {}


class GenerateFinalAnswerNode:
    """Generates the final answer."""

    def __call__(self, state: COTState):
        logging.info("Generating final answer")
        model = state.model
        # Ask the assistant to provide the final answer

        messages = state.messages + \
            [HumanMessage(content=CoTPrompts.FINAL_PROMPT)]

        response = model.invoke(messages)
        state.final_answer = response.content
        state.messages.append(response)

        return {}


def EDGE_should_continue(state: COTState) -> bool:
    return state.next_action != 'final_answer' and state.step_count < state.max_steps


def build_cot_graph():
    """Builds the Chain-of-Thought reasoning graph."""
    graph_builder = StateGraph(COTState)

    # Add nodes
    graph_builder.add_node("generate_step", GenerateStepNode())
    graph_builder.add_node("generate_final_answer", GenerateFinalAnswerNode())

    # Configure edges
    graph_builder.add_edge(START, "generate_step")
    graph_builder.add_conditional_edges(
        "generate_step",
        EDGE_should_continue,
        {True: "generate_step", False: "generate_final_answer"}
    )
    graph_builder.add_edge("generate_final_answer", END)

    return graph_builder.compile()


class CoT:
    """Main class for Chain-of-Thought reasoning."""

    def __init__(self, model=None):
        if model is None:
            self.model = SeedGen2GenerativeModel().json_model
        else:
            self.model = model

    def invoke(self, prompt: List[AnyMessage]) -> AIMessage:
        """
        Runs the chain-of-thought reasoning process.

        Args:
            prompt: The input prompt for reasoning.

        Returns:
            The final answer generated by the model.
        """
        graph = build_cot_graph()

        initial_state = COTState(
            model=self.model,
            messages=[
                HumanMessage(content=CoTPrompts.PROMPT_COT),
                *prompt,
                AIMessage(
                    content="Thank you! I will now think step by step following my instructions, starting at the beginning after decomposing the problem.")
            ],
            step_count=0,
            max_steps=25,
            next_action="continue"
        )

        graph.invoke(initial_state)
        if initial_state.final_answer is None:
            raise ValueError("No final answer generated")
        return AIMessage(content=initial_state.final_answer)
