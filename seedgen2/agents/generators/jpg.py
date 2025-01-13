#!/usr/bin/env python3
"""
Generate random baseline JPEG files without using any non-standard Python modules.

This script constructs a minimal valid JPEG by:
  1. Writing the minimal required markers in the correct order.
  2. Randomizing the quantization tables, Huffman tables, and image data.
  3. Outputting the final byte stream to a file.

Note:
  - This script attempts to produce "valid enough" baseline JPEGs for typical decoders.
  - It does not cover every aspect of the JPEG specification (e.g., progressive JPEG, arithmetic coding, etc.).
  - Use at your own risk, as some decoders may still reject heavily randomized data.
"""

import os
import random
import struct

def write_jpeg_header(out_file):
    """
    Write the Start Of Image marker (SOI) and a minimal JFIF APP0 segment.
    """
    # SOI marker
    out_file.write(b'\xFF\xD8')  
    
    # APP0 (JFIF) marker (FFE0), length = 16 (excluding marker and length bytes)
    # Identifier: 'JFIF\0', version, density, etc.
    app0 = (
        b'\xFF\xE0'        # APP0 marker
        b'\x00\x10'        # 16 bytes length
        b'JFIF\x00'        # Identifier
        b'\x01\x02'        # Version 1.02
        b'\x00'            # Units = 0 (no density)
        b'\x00\x01\x00\x01'# Xdensity=1, Ydensity=1
        b'\x00\x00'        # Thumbnail width=0, height=0
    )
    out_file.write(app0)

def write_dqt_segment(out_file, num_tables=2):
    """
    Write one or more DQT (Define Quantization Table) segments.
    We'll generate random 8x8 quant tables for both luminance (table 0) and
    chrominance (table 1) if requested.
    """
    # Each DQT segment: marker (FFDB), length, [precision+tableID], 64 bytes of table data.
    # We can put multiple tables in one segment or separate them.
    
    # Collect all table data first
    table_data = b''
    for table_id in range(num_tables):
        # 8 bits for each quant value => Pq=0
        # high nibble = 0 (8-bit values), low nibble = table_id
        precision_and_id = (0 << 4) | table_id  
        table_data += struct.pack('B', precision_and_id)
        
        # 64 random quant values between 1 and 255 (cannot be 0)
        for _ in range(64):
            qv = random.randint(1, 255)
            table_data += struct.pack('B', qv)
    
    # marker + length (2 bytes). Length = 2 + (#tables * (1 + 64))
    # If num_tables=2, total bytes for tables = 2*(1+64) = 130
    # segment length = 2 (bytes for length itself) + 130 = 132
    segment_length = 2 + len(table_data)
    
    dqt_header = (
        b'\xFF\xDB' +
        struct.pack('>H', segment_length)
    )
    
    out_file.write(dqt_header)
    out_file.write(table_data)

def write_sof0_segment(out_file, width, height, num_components=3):
    """
    Write the Baseline SOF0 (Start of Frame) marker.
    """
    # We will assume 8 bits per sample
    bits_per_sample = 8
    
    # length = 8 + 3*num_components
    # For 3 components (YCbCr), length = 8 + 3*3 = 17
    frame_header_length = 8 + (num_components * 3)
    
    sof0_header = b'\xFF\xC0' + struct.pack('>H', frame_header_length)
    
    # Write sample precision, image height, width
    sof0_header += struct.pack('>BHH', bits_per_sample, height, width)
    
    # Number of components (usually 3 for color)
    sof0_header += struct.pack('B', num_components)
    
    # For each component, define an ID, subsampling factors, and quant table ID
    # Standard baseline is Y=1,2,2 for subsampling, Cb=2,1,1, etc. 
    # We'll do something random but valid.
    for comp_id in range(1, num_components+1):
        # Component ID
        sof0_header += struct.pack('B', comp_id)
        # Horizontal and vertical sampling factors (4 bits each)
        # Typically Y has 2x2, Cb/Cr have 1x1. We'll randomize but keep them in [1..2].
        h_samp = random.randint(1, 2)
        v_samp = random.randint(1, 2)
        sampling = (h_samp << 4) | (v_samp & 0x0F)
        sof0_header += struct.pack('B', sampling)
        # Quant table ID (0 or 1)
        sof0_header += struct.pack('B', random.randint(0, 1))
    
    out_file.write(sof0_header)

def write_dht_segment(out_file, num_tables=2):
    """
    Write Huffman tables (DHT). We'll generate random "reasonable" Huffman tables.
    """
    # The DHT format:
    #   0xFF, 0xC4
    #   length (2 bytes)
    #
    #   For each table:
    #     1 byte = [class (4 bits) | id (4 bits)]
    #     16 bytes = number of symbols of each code length (1..16)
    #     N bytes = the actual symbols, where N = sum of the 16 code-length counts
    #
    # We'll generate both DC (class=0) and AC (class=1) tables for either Y or C.
    # However, to keep things short, we might just generate a small random set.
    
    # We'll store the “chunks” for each table, then compute the total length.
    table_chunks = []
    
    # Let’s define 2*2=4 tables: DC0, AC0, DC1, AC1
    # But we’ll limit to whatever `num_tables` is (1..4 in practice).
    # If num_tables=2, we do DC0, AC0. If 4, we also do DC1, AC1, etc.
    
    max_table_count = min(num_tables * 2, 4)  # Each "num_tables" means DC+AC for that ID
    for table_id in range(max_table_count):
        # table_id goes 0..3
        # half are DC class=0, half are AC class=1
        # e.g. table_id=0 -> DC, ID=0
        #      table_id=1 -> AC, ID=0
        #      table_id=2 -> DC, ID=1
        #      table_id=3 -> AC, ID=1
        
        ht_class = (table_id % 2)  # 0=DC, 1=AC
        ht_id    = (table_id // 2)
        
        class_id_byte = (ht_class << 4) | ht_id
        
        # For code-length counts, let's generate a random distribution that sums up to some small N
        # But we must ensure total symbols <= 16 for DC or <= 256 for AC. Let's keep it small anyway.
        code_length_counts = []
        total_symbols = 0
        
        # A trick: generate random distribution in 16 buckets (for lengths 1..16)
        # We also want at least 1 symbol in total.
        while total_symbols == 0:
            code_length_counts = [random.randint(0, 3) for _ in range(16)]
            total_symbols = sum(code_length_counts)
        
        # Now generate that many symbols in ascending order
        symbols = list(range(1, total_symbols + 1))
        random.shuffle(symbols)
        
        # Build the chunk
        chunk = struct.pack('B', class_id_byte)
        # 16 bytes of code-length counts
        for c in code_length_counts:
            chunk += struct.pack('B', c)
        # N bytes of symbols
        for sym in symbols:
            # symbol must be in range [0..255]
            chunk += struct.pack('B', sym & 0xFF)
        
        table_chunks.append(chunk)
    
    # Compute total length
    tables_data = b''.join(table_chunks)
    segment_length = 2 + len(tables_data)  # length includes itself
    
    dht_header = b'\xFF\xC4' + struct.pack('>H', segment_length)
    out_file.write(dht_header)
    out_file.write(tables_data)

def write_sos_segment(out_file, num_components=3):
    """
    Write the Start of Scan marker and minimal scan header.
    """
    # For each component in the scan, we specify the component ID and
    # which DC/AC Huffman table to use (high nibble=DC, low nibble=AC).
    #
    # We'll just attach them all to table 0 or 1 at random, ignoring typical Y/Cb/Cr defaults.
    #
    # The length of SOS is 6 + 2 * num_components
    length_sos = 6 + (2 * num_components)
    
    sos_header = (
        b'\xFF\xDA' +
        struct.pack('>H', length_sos) +
        struct.pack('B', num_components)
    )
    
    for comp_id in range(1, num_components+1):
        # component ID
        sos_header += struct.pack('B', comp_id)
        # DC/AC table selection
        dc_tbl = random.randint(0, 1)
        ac_tbl = random.randint(0, 1)
        sos_header += struct.pack('B', (dc_tbl << 4) | ac_tbl)
    
    # Spectral selection and approx bits (for progressive JPEG),
    # but in baseline these are 0..63, 0
    sos_header += b'\x00\x3F\x00'
    
    out_file.write(sos_header)

def write_compressed_scan_data(out_file, width, height, num_components=3):
    """
    Write random entropy-coded data. Strictly speaking, this is the most complex
    part of JPEG (Huffman encoding). For this "fuzzer" approach, we'll just dump
    random bytes that start with 0xFF, 0x00 escaping and hope some decoders accept it.
    
    A truly valid approach would Huffman-encode real MCUs. This is just a random filler
    that might pass in some decoders but is definitely not a correct encoding.
    """
    # Typically the size in MCUs depends on sampling factors and all. We'll just pick
    # some arbitrary number of bytes and fill them with random values, carefully escaping 0xFF.
    
    # We'll attempt a small-ish random chunk
    num_bytes = (width * height * num_components) // 8 + 64
    # To avoid accidental marker insertion, each 0xFF must be followed by 0x00 in compressed data.
    # We'll randomly generate and insert the 0x00 after each 0xFF.
    
    raw_data = bytearray()
    for _ in range(num_bytes):
        val = random.randint(0, 255)
        raw_data.append(val)
        if val == 0xFF:
            raw_data.append(0x00)  # escape
    
    out_file.write(bytes(raw_data))

def write_eoi_marker(out_file):
    """
    Write the End Of Image marker.
    """
    out_file.write(b'\xFF\xD9')

def generate_random_jpeg(output_path):
    """
    Generate a single random JPEG file and write it to output_path.
    """
    # Random image dimensions (within some small range to keep file size moderate)
    width = random.randint(16, 256)
    height = random.randint(16, 256)
    
    # Random number of components: either 1 (grayscale) or 3 (color)
    num_components = random.choice([1, 3])
    
    with open(output_path, 'wb') as f:
        # Write minimal headers
        write_jpeg_header(f)
        
        # Define random quantization tables
        # If we have 3 components, we might want 2 tables (luma/chroma).
        # If grayscale, 1 table is enough. We'll decide randomly.
        dqt_tables = 2 if num_components == 3 else 1
        write_dqt_segment(f, num_tables=dqt_tables)
        
        # Write SOF0 (Baseline) specifying width, height, # components
        write_sof0_segment(f, width, height, num_components=num_components)
        
        # Write DHT segments. For each quant table, we might define DC+AC Huffman tables.
        # We'll just randomly pick up to 2 or 3 here.
        huff_tables = random.randint(1, 2)  # up to 2 sets, each is DC+AC
        write_dht_segment(f, num_tables=huff_tables)
        
        # Start of Scan
        write_sos_segment(f, num_components=num_components)
        
        # Random "compressed" scan data (not truly valid Huffman, but often decodable enough)
        write_compressed_scan_data(f, width, height, num_components)
        
        # End Of Image
        write_eoi_marker(f)
