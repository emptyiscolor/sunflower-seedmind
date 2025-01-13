#!/usr/bin/env python3
"""
generate_random_jpegs.py

A script to generate random JPEG files that cover a variety of
features such as dimensions, color modes, quality, progressive encoding,
and randomized EXIF metadata.

Requires:
    - Pillow (pip install Pillow)
    - piexif (pip install piexif)
"""

import os
import random
import string
from io import BytesIO

import numpy as np
from PIL import Image
import piexif

def generate_random_pixel_data(width, height, mode):
    """
    Generate random pixel data for a given size and color mode.
    """
    if mode == "RGB":
        # 3 channels
        data = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
        return Image.fromarray(data, mode)
    elif mode == "L":
        # 1 channel (grayscale)
        data = np.random.randint(0, 256, (height, width), dtype=np.uint8)
        return Image.fromarray(data, mode)
    elif mode == "RGBA":
        # 4 channels (with alpha)
        data = np.random.randint(0, 256, (height, width, 4), dtype=np.uint8)
        return Image.fromarray(data, mode)
    else:
        # Default to RGB if not recognized
        data = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
        return Image.fromarray(data, "RGB")

def generate_random_exif():
    """
    Generate a random EXIF dictionary using piexif.
    We will fill in a few common EXIF fields with random values/strings.
    """
    # Create a minimal EXIF dict with the sections we may fill in
    exif_dict = {
        "0th": {},
        "Exif": {},
        "GPS": {},
        "1st": {},
        "Interop": {},
        "thumbnail": None,
    }

    # 0th IFD (primary) tags
    exif_dict["0th"][piexif.ImageIFD.Make] = random_string().encode("utf-8")
    exif_dict["0th"][piexif.ImageIFD.Model] = random_string().encode("utf-8")
    exif_dict["0th"][piexif.ImageIFD.Software] = random_string().encode("utf-8")

    # EXIF IFD tags
    exif_dict["Exif"][piexif.ExifIFD.ExifVersion] = b"0221"
    exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = random_date().encode("utf-8")
    exif_dict["Exif"][piexif.ExifIFD.LensMake] = random_string().encode("utf-8")
    exif_dict["Exif"][piexif.ExifIFD.LensModel] = random_string().encode("utf-8")

    # GPS IFD tags (random latitude, longitude)
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = random.choice([b"N", b"S"])
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = random.choice([b"E", b"W"])
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = to_gps_tuple(
        random.uniform(0, 90)
    )
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = to_gps_tuple(
        random.uniform(0, 180)
    )

    return exif_dict

def random_string(length=8):
    """
    Generate a random ASCII string of given length.
    """
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def random_date():
    """
    Generate a random EXIF-compatible date in the format YYYY:MM:DD HH:MM:SS.
    """
    year = random.randint(2000, 2030)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    hour = random.randint(0, 23)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return f"{year}:{month:02}:{day:02} {hour:02}:{minute:02}:{second:02}"

def to_gps_tuple(value):
    """
    Convert a float GPS coordinate into the EXIF rational tuple format:
    e.g., 35.6895 -> [(35, 1), (41, 1), (37079, 1000)] for 35°41'37.079".
    """
    # Degrees
    degrees = int(value)
    # Minutes
    minutes = int((value - degrees) * 60)
    # Seconds
    seconds = int(round(((value - degrees) * 60 - minutes) * 60 * 1000))
    return [
        (degrees, 1),
        (minutes, 1),
        (seconds, 1000),
    ]

def generate_random_jpeg(
    output_path, 
    width=None, 
    height=None, 
    mode=None, 
    quality=None, 
    progressive=None
):
    """
    Generates a single random JPEG file with diverse parameters and EXIF data.
    """

    # Randomly pick width, height if not provided
    if width is None:
        width = random.randint(64, 1024)
    if height is None:
        height = random.randint(64, 1024)

    # Randomly pick mode if not provided
    if mode is None:
        mode = random.choice(["L", "RGB", "RGBA"])

    # Randomly pick JPEG quality (1 to 95 is typical range)
    if quality is None:
        quality = random.randint(1, 95)

    # Randomly decide if it's progressive
    if progressive is None:
        progressive = random.choice([True, False])

    # Generate the random image
    img = generate_random_pixel_data(width, height, mode)

    # Generate random EXIF metadata
    exif_dict = generate_random_exif()
    exif_bytes = piexif.dump(exif_dict)

    # Randomly select a subsampling mode (if Pillow version supports it)
    # Options: 0 = 4:4:4, 1 = 4:2:2, 2 = 4:2:0
    # Some Pillow versions only support 0,1,2. Others might require different approach.
    subsampling = random.choice([0, 1, 2])

    # Save the image as JPEG in the specified output path
    img.save(
        output_path,
        format="JPEG",
        quality=quality,
        progressive=progressive,
        subsampling=subsampling,
        optimize=True,  # Attempt to optimize Huffman tables
        exif=exif_bytes
    )
