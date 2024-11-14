from langchain_core.messages import HumanMessage, AIMessage, AnyMessage
from seedgen2.agent.cot import CoT
import logging

from seedgen2.agent.presets import SeedGen2GenerativeModel

logging.basicConfig(level=logging.INFO)


prompt = """
My Mazda CX-30 (purchased last year):
Purchase Price: $30,000 (out-the-door)
Current Trade-In Value: Approximately $19,633 

FYI, For the same CX-30:
Estimated Monthly Payment for 36-Month Lease: Approximately $249 with $2,999 due at signing 

Tesla Model 3 Pricing:
Long Range All-Wheel Drive (AWD): Starting at $47,490

I'm thinking change my car from mazda to the tesla model 3. I want to make wise decisions. Based on those information, give me details (with numbers and explanations) about the transition, is it worth it or should I just wait one or two more years.
"""

print("COT result:")
model = CoT(model=SeedGen2GenerativeModel().model,
            json_model=SeedGen2GenerativeModel().json_model)
print(model.invoke([HumanMessage(content=prompt)]).content)

print("Normal result:")
model = SeedGen2GenerativeModel().model
print(model.invoke([HumanMessage(content=prompt)]).content)
