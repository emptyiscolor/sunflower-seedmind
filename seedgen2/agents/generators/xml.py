#!/usr/bin/env python3

import random
import string
import sys

def random_tag_name(min_len=3, max_len=8):
    """
    Generate a random tag name with letters (no digits at start to keep it valid).
    """
    length = random.randint(min_len, max_len)
    # Tag names cannot start with digits or certain punctuation, so ensure it starts with a letter.
    first_char = random.choice(string.ascii_letters)
    other_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=length - 1))
    return first_char + other_chars

def random_text(min_len=5, max_len=30):
    """
    Generate random text content, which may include letters, digits, and spaces.
    """
    length = random.randint(min_len, max_len)
    # Include basic ASCII letters, digits, and spaces
    chars = string.ascii_letters + string.digits + " "
    return ''.join(random.choice(chars) for _ in range(length))

def random_attributes(max_attrs=3):
    """
    Generate a dictionary of random attributes.
    """
    attrs = {}
    num_attrs = random.randint(0, max_attrs)
    for _ in range(num_attrs):
        attr_name = random_tag_name()
        attr_value = random_text(3, 12)
        # Escape attribute quotes if needed
        attr_value = attr_value.replace('"', '&quot;')
        attrs[attr_name] = attr_value
    return attrs

def random_comment():
    """
    Generate a random XML comment.
    """
    return "<!-- " + random_text(10, 30) + " -->"

def random_cdata():
    """
    Generate a random CDATA section.
    """
    return "<![CDATA[" + random_text(10, 30) + "]]>"

def random_processing_instruction():
    """
    Generate a random processing instruction, e.g. <?target data?>
    """
    target = random_tag_name(3, 6)
    data = random_text(5, 15)
    # Avoid '?' in data to prevent premature closing of PI
    data = data.replace('?', '')
    return f"<?{target} {data}?>"

def create_element(level=0, max_depth=3):
    """
    Recursively create an XML element (as a string) with:
      - Random name
      - Random attributes
      - Random text / child elements
      - Optional comments, processing instructions, CDATA.
    """
    # Chance to insert a comment, processing instruction, or CDATA before element
    leading_chunks = []
    # Random chance for comment
    if random.random() < 0.2:  # 20% chance
        leading_chunks.append(random_comment())
    # Random chance for processing instruction
    if random.random() < 0.2:  # 20% chance
        leading_chunks.append(random_processing_instruction())
    # Random chance for CDATA
    if random.random() < 0.2:  # 20% chance
        leading_chunks.append(random_cdata())

    # Build the element
    tag_name = random_tag_name()
    attrs = random_attributes()

    # Start opening tag
    element_str = "".join(leading_chunks) + f"<{tag_name}"

    # Add attributes
    for k, v in attrs.items():
        element_str += f' {k}="{v}"'

    element_str += ">"

    # Decide whether to add text or child elements
    # or possibly embed a comment / CDATA in the middle
    if level < max_depth and random.random() < 0.6:
        # Make child elements
        num_children = random.randint(1, 3)
        for _ in range(num_children):
            element_str += create_element(level + 1, max_depth)
    else:
        # Just add random text content
        # Possibly sprinkle in a mid-element comment/CDATA as well
        if random.random() < 0.3:
            element_str += random_comment()
        if random.random() < 0.3:
            element_str += random_cdata()
        element_str += random_text(5, 20)

    # Close tag
    element_str += f"</{tag_name}>"
    return element_str

def generate_random_xml(max_depth=3):
    """
    Generate a random XML document as a string.
    Includes optional top-level processing instructions and comments.
    """
    # Possible leading items before the root element
    doc_chunks = []
    # XML declaration
    doc_chunks.append('<?xml version="1.0" encoding="UTF-8"?>')

    # Optional top-level comment
    if random.random() < 0.3:
        doc_chunks.append(random_comment())

    # Optional top-level processing instruction
    if random.random() < 0.3:
        doc_chunks.append(random_processing_instruction())

    # Create the root element (and its children)
    root_element = create_element(level=0, max_depth=max_depth)
    doc_chunks.append(root_element)

    return "\n".join(doc_chunks)
