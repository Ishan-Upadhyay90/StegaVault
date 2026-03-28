from flask import Flask, request, send_file, render_template_string, session, redirect, url_for, jsonify, Response
import cv2
import os
import uuid
import re
import threading
import time
import math
import struct
import json
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
import numpy as np

app = Flask(__name__)
app.secret_key = "stegavault_super_secret_key_2024"
UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Maximum file size (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Progress tracking dictionary
progress_tracking = {}

# =========================
# CIPHER FUNCTIONS
# =========================

def caesar_encrypt(text, key):
    result = ""
    key = int(key)
    for char in text:
        if char.isalpha():
            shift = 65 if char.isupper() else 97
            result += chr((ord(char) - shift + key) % 26 + shift)
        else:
            result += char
    return result

def caesar_decrypt(text, key):
    return caesar_encrypt(text, -int(key))

def vigenere_encrypt(text, key):
    result = ""
    key = key.lower()
    key_index = 0
    for char in text:
        if char.isalpha():
            shift = ord(key[key_index % len(key)]) - 97
            base = 65 if char.isupper() else 97
            result += chr((ord(char) - base + shift) % 26 + base)
            key_index += 1
        else:
            result += char
    return result

def vigenere_decrypt(text, key):
    result = ""
    key = key.lower()
    key_index = 0
    for char in text:
        if char.isalpha():
            shift = ord(key[key_index % len(key)]) - 97
            base = 65 if char.isupper() else 97
            result += chr((ord(char) - base - shift) % 26 + base)
            key_index += 1
        else:
            result += char
    return result

# =========================
# TEXT STEGANOGRAPHY
# =========================

def get_image_capacity(img):
    """Calculate maximum bytes that can be stored in image"""
    if img is None:
        return 0
    # Each pixel has 3 channels (RGB), each channel can store 1 bit
    # So capacity in bytes = (width * height * 3) / 8
    capacity_bytes = (img.shape[0] * img.shape[1] * 3) // 8
    # Reserve some space for metadata and EOF marker
    return capacity_bytes - 100  # Leave buffer for safety

def encode_text_in_image(image_path, message):
    img = cv2.imread(image_path)
    if img is None:
        return None
    
    message += "#####"
    binary_message = ''.join(format(ord(c), '08b') for c in message)
    
    max_capacity = img.shape[0] * img.shape[1] * 3
    if len(binary_message) > max_capacity:
        return None
    
    data_index = 0
    for row in img:
        for pixel in row:
            for i in range(3):
                if data_index < len(binary_message):
                    pixel[i] = pixel[i] & 254 | int(binary_message[data_index])
                    data_index += 1
    
    encoded_path = os.path.join(UPLOAD_FOLDER, f"encoded_text_{uuid.uuid4().hex}.png")
    cv2.imwrite(encoded_path, img)
    return encoded_path

def decode_text_from_image(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return None
    
    binary_data = ""
    for row in img:
        for pixel in row:
            for i in range(3):
                binary_data += str(pixel[i] & 1)
    
    message = ""
    for i in range(0, len(binary_data), 8):
        byte = binary_data[i:i+8]
        if len(byte) < 8:
            break
        message += chr(int(byte, 2))
        if message.endswith("#####"):
            break
    
    return message[:-5] if message.endswith("#####") else None

# =========================
# IMPROVED FILE STEGANOGRAPHY
# =========================

def file_to_bytes(file_path):
    """Read file and return bytes"""
    with open(file_path, "rb") as f:
        return f.read()

def encode_file_in_image(image_path, file_path, session_id=None):
    """Encode any file (including PDFs) into image with proper binary handling"""
    img = cv2.imread(image_path)
    if img is None:
        return None
    
    # Read file data
    file_bytes = file_to_bytes(file_path)
    filename = os.path.basename(file_path)
    file_size = len(file_bytes)
    
    # Calculate total capacity
    total_pixels = img.shape[0] * img.shape[1]
    total_bits = total_pixels * 3
    capacity_bytes = total_bits // 8
    
    # Create header with filename length and filename
    # Format: [4 bytes for filename length][filename bytes][4 bytes for file size][file bytes]
    filename_bytes = filename.encode('utf-8')
    filename_len = len(filename_bytes)
    
    # Header structure: filename_len (4 bytes) + filename + file_size (4 bytes)
    header = struct.pack('>I', filename_len) + filename_bytes + struct.pack('>I', file_size)
    header_size = len(header)
    
    # Total required bytes = header + file
    total_required_bytes = header_size + file_size
    
    if total_required_bytes > capacity_bytes:
        return None
    
    # Combine header and file data
    combined_data = header + file_bytes
    
    # Convert to binary - ensure perfect byte representation
    binary_data = []
    for byte in combined_data:
        binary_data.extend([(byte >> i) & 1 for i in range(7, -1, -1)])
    
    total_bits_to_encode = len(binary_data)
    
    # Encode into image
    data_index = 0
    flat_img = img.reshape(-1, 3)  # Flatten the image for easier processing
    
    for idx in range(len(flat_img)):
        if data_index >= total_bits_to_encode:
            break
        pixel = flat_img[idx]
        for channel in range(3):
            if data_index < total_bits_to_encode:
                pixel[channel] = pixel[channel] & 254 | binary_data[data_index]
                data_index += 1
                
                # Report progress
                if session_id and session_id in progress_tracking:
                    progress = (data_index / total_bits_to_encode) * 100
                    progress_tracking[session_id]['encode'] = progress
    
    # Reshape back to original dimensions
    img_encoded = flat_img.reshape(img.shape)
    
    output_path = os.path.join(UPLOAD_FOLDER, f"encoded_file_{uuid.uuid4().hex}.png")
    cv2.imwrite(output_path, img_encoded)
    
    if session_id and session_id in progress_tracking:
        progress_tracking[session_id]['encode'] = 100
    
    return output_path

def decode_file_from_image(image_path, session_id=None):
    """Extract any file (including PDFs) from image with proper binary reconstruction"""
    img = cv2.imread(image_path)
    if img is None:
        return None, None
    
    total_pixels = img.shape[0] * img.shape[1]
    total_bits = total_pixels * 3
    
    # Extract all LSB bits - store as list of ints for efficiency
    extracted_bits = []
    flat_img = img.reshape(-1, 3)
    
    for idx, pixel in enumerate(flat_img):
        for channel in range(3):
            extracted_bits.append(pixel[channel] & 1)
            
            # Report progress for early extraction
            if session_id and session_id in progress_tracking:
                progress = (len(extracted_bits) / total_bits) * 50  # First 50% for extraction
                progress_tracking[session_id]['decode'] = progress
    
    # Need at least 8 bytes (64 bits) for header
    if len(extracted_bits) < 64:
        return None, None
    
    # Convert bits to bytes for header parsing
    def bits_to_bytes(bits):
        """Convert list of bits to bytes"""
        bytes_list = []
        for i in range(0, len(bits) - 7, 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | bits[i + j]
            bytes_list.append(byte)
        return bytes(bytes_list)
    
    # Parse header
    header_bytes = bits_to_bytes(extracted_bits[:32])  # First 4 bytes for filename length
    filename_len = struct.unpack('>I', header_bytes[:4])[0]
    
    # Calculate positions
    filename_bits_start = 32
    filename_bits_end = filename_bits_start + (filename_len * 8)
    
    if filename_bits_end + 32 > len(extracted_bits):
        return None, None
    
    # Extract filename
    filename_bytes = bits_to_bytes(extracted_bits[filename_bits_start:filename_bits_end])
    try:
        filename = filename_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return None, None
    
    # Extract file size
    file_size_start = filename_bits_end
    file_size_end = file_size_start + 32
    file_size_bytes = bits_to_bytes(extracted_bits[file_size_start:file_size_end])
    file_size = struct.unpack('>I', file_size_bytes[:4])[0]
    
    # Extract file data
    file_data_start = file_size_end
    file_data_end = file_data_start + (file_size * 8)
    
    if file_data_end > len(extracted_bits):
        return None, None
    
    # Extract and reconstruct file bytes
    file_bits = extracted_bits[file_data_start:file_data_end]
    file_bytes = bits_to_bytes(file_bits)
    
    # Verify we got the expected size
    if len(file_bytes) != file_size:
        print(f"Size mismatch: expected {file_size}, got {len(file_bytes)}")
        return None, None
    
    # Save the file with original name
    output_path = os.path.join(UPLOAD_FOLDER, f"decoded_{filename}")
    with open(output_path, "wb") as f:
        f.write(file_bytes)
    
    # Verify file integrity for common formats
    if filename.endswith('.pdf'):
        # Check PDF magic number
        if file_bytes[:4] != b'%PDF':
            print("Warning: Extracted file may not be a valid PDF")
    
    if session_id and session_id in progress_tracking:
        progress_tracking[session_id]['decode'] = 100
    
    return output_path, filename

def get_file_size_info(file_size):
    """Convert file size to human readable format"""
    if file_size < 1024:
        return f"{file_size} B"
    elif file_size < 1024 * 1024:
        return f"{file_size / 1024:.2f} KB"
    else:
        return f"{file_size / (1024 * 1024):.2f} MB"

# =========================
# PROGRESS TRACKING ENDPOINT
# =========================

@app.route("/progress/<session_id>")
def get_progress(session_id):
    """Endpoint for real-time progress updates"""
    def generate():
        last_progress = {'encode': 0, 'decode': 0}
        while session_id in progress_tracking:
            current = progress_tracking.get(session_id, {'encode': 0, 'decode': 0})
            if current != last_progress:
                last_progress = current.copy()
                yield f"data: {json.dumps(current)}\n\n"
            time.sleep(0.1)
            # Remove session after 30 seconds of inactivity
            if time.time() - progress_tracking.get(session_id, {}).get('timestamp', 0) > 30:
                break
        yield f"data: {json.dumps({'encode': 100, 'decode': 100, 'complete': True})}\n\n"
    
    return Response(generate(), mimetype="text/event-stream")

# =========================
# HTML TEMPLATE (With Real Progress Bars)
# =========================

MASTER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StegaVault | Secure Steganography Suite</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #eef2f7 100%);
            min-height: 100vh;
            color: #1a2c3e;
        }
        
        /* Glass navigation */
        .nav-premium {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(0,0,0,0.05);
            padding: 1rem 0;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 2px 20px rgba(0,0,0,0.05);
        }
        .brand {
            font-weight: 800;
            font-size: 1.8rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            letter-spacing: -0.5px;
        }
        .brand i {
            background: none;
            -webkit-background-clip: unset;
            color: #667eea;
            margin-right: 6px;
        }
        .nav-links {
            display: flex;
            gap: 0.5rem;
            background: rgba(0,0,0,0.02);
            padding: 0.3rem;
            border-radius: 60px;
            border: 1px solid rgba(0,0,0,0.05);
        }
        .nav-btn {
            padding: 0.6rem 1.8rem;
            border-radius: 40px;
            font-weight: 600;
            transition: all 0.25s ease;
            background: transparent;
            border: none;
            color: #5a6e7c;
            text-decoration: none;
            display: inline-block;
        }
        .nav-btn i { margin-right: 8px; }
        .nav-btn.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }
        .nav-btn:hover:not(.active) {
            background: rgba(102, 126, 234, 0.1);
            color: #667eea;
        }
        .card-modern {
            background: white;
            border-radius: 24px;
            border: none;
            box-shadow: 0 10px 30px rgba(0,0,0,0.05);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .card-modern:hover {
            box-shadow: 0 15px 40px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }
        .form-control, .form-select {
            background: #f8f9fa;
            border: 1px solid #e1e8ed;
            color: #1a2c3e;
            border-radius: 16px;
            padding: 0.8rem 1.2rem;
            transition: all 0.2s;
        }
        .form-control:focus, .form-select:focus {
            background: white;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            color: #1a2c3e;
        }
        .btn-primary-gradient {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 40px;
            padding: 0.8rem;
            font-weight: 600;
            transition: all 0.2s;
            color: white;
        }
        .btn-primary-gradient:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
        }
        .btn-primary-gradient:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .btn-outline-accent {
            border: 2px solid #667eea;
            background: transparent;
            border-radius: 40px;
            color: #667eea;
            font-weight: 600;
            transition: all 0.2s;
        }
        .btn-outline-accent:hover {
            background: #667eea;
            color: white;
            transform: translateY(-1px);
        }
        .result-box {
            background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
            border-radius: 20px;
            padding: 1.5rem;
            border-left: 4px solid #667eea;
            word-break: break-all;
        }
        .badge-cipher {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 4px 12px;
            border-radius: 50px;
            font-size: 0.75rem;
            color: white;
        }
        footer {
            text-align: center;
            padding: 2rem;
            border-top: 1px solid rgba(0,0,0,0.05);
            margin-top: 3rem;
            color: #5a6e7c;
        }
        
        /* Progress Bar Styles */
        .progress-container {
            margin-top: 1rem;
            display: none;
        }
        .progress {
            height: 8px;
            border-radius: 10px;
            background: #e1e8ed;
            overflow: hidden;
        }
        .progress-bar {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            transition: width 0.3s ease;
        }
        .progress-text {
            font-size: 0.85rem;
            color: #667eea;
            margin-top: 0.5rem;
            font-weight: 500;
        }
        
        /* Size indicator */
        .size-badge {
            font-size: 0.75rem;
            padding: 4px 10px;
            background: #f0f2f5;
            border-radius: 12px;
            color: #5a6e7c;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px);}
            to { opacity: 1; transform: translateY(0);}
        }
        .page-content {
            animation: fadeIn 0.4s ease-out;
        }
        
        .file-info {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 0.75rem;
            margin-top: 0.5rem;
            font-size: 0.85rem;
        }
        
        .alert-warning {
            background: #fff3cd;
            border: 1px solid #ffc107;
            color: #856404;
            border-radius: 12px;
        }
        
        .spinner-border-sm {
            width: 1rem;
            height: 1rem;
            border-width: 0.15em;
        }
    </style>
</head>
<body>

<!-- Navigation -->
<div class="nav-premium">
    <div class="container">
        <div class="d-flex flex-wrap justify-content-between align-items-center">
            <div class="brand">
                <i class="fas fa-shield-hooded"></i> StegaVault
            </div>
            <div class="nav-links">
                <a href="?page=text" class="nav-btn {% if active_page == 'text' %}active{% endif %}">
                    <i class="fas fa-envelope"></i> Text Vault
                </a>
                <a href="?page=file" class="nav-btn {% if active_page == 'file' %}active{% endif %}">
                    <i class="fas fa-file-archive"></i> File Vault
                </a>
            </div>
        </div>
    </div>
</div>

<div class="container py-4">
    <div class="page-content">
        {% if active_page == 'text' %}
        <!-- ==================== TEXT STEGANOGRAPHY PAGE ==================== -->
        <div class="row g-4">
            <div class="col-lg-6">
                <div class="card-modern p-4 h-100">
                    <h3 class="mb-3"><i class="fas fa-lock me-2" style="color:#667eea;"></i> Encode Secret Text</h3>
                    <form id="encodeTextForm" method="POST" enctype="multipart/form-data">
                        <input type="hidden" name="action" value="encode_text">
                        <label class="form-label fw-semibold">Cover Image</label>
                        <input type="file" name="image" class="form-control mb-3" accept="image/*" required id="coverImageInput">
                        
                        <div id="imageCapacity" class="file-info mb-3" style="display: none;">
                            <i class="fas fa-database me-2"></i> <span id="capacityText">Calculating capacity...</span>
                        </div>
                        
                        <label class="form-label fw-semibold">Secret Message</label>
                        <textarea name="message" id="secretMessage" rows="3" class="form-control mb-3" placeholder="Your confidential text..." required></textarea>
                        
                        <div id="messageSize" class="file-info mb-3" style="display: none;">
                            <i class="fas fa-font me-2"></i> Message size: <span id="messageSizeText">0</span> bytes
                        </div>
                        
                        <div class="row g-2 mb-3">
                            <div class="col-md-5">
                                <select name="cipher" id="cipherSelectText" class="form-select" onchange="updateKeyPlaceholderText()">
                                    <option value="caesar">🔑 Caesar Cipher</option>
                                    <option value="vigenere">🔤 Vigenère Cipher</option>
                                </select>
                            </div>
                            <div class="col-md-7">
                                <input type="text" name="key" id="keyInputText" class="form-control" placeholder="Shift number (e.g., 3)">
                            </div>
                        </div>
                        
                        <button type="button" onclick="encryptClientText()" class="btn btn-outline-accent w-100 mb-3">
                            <i class="fas fa-magic"></i> Encrypt Message
                        </button>
                        
                        <textarea id="encryptedResult" class="form-control mb-3" rows="2" placeholder="Encrypted text preview..." readonly style="background:#f8f9fa;"></textarea>
                        <input type="hidden" name="final_message" id="finalEncryptedMsg">
                        
                        <div class="progress-container" id="textProgressContainer">
                            <div class="progress">
                                <div class="progress-bar" id="textProgressBar" style="width: 0%"></div>
                            </div>
                            <div class="progress-text text-center" id="textProgressText">Preparing...</div>
                        </div>
                        
                        <button type="submit" name="encode_submit" class="btn btn-primary-gradient w-100 mt-3">
                            <i class="fas fa-arrow-down"></i> Encode & Download Image
                        </button>
                    </form>
                </div>
            </div>
            
            <div class="col-lg-6">
                <div class="card-modern p-4 h-100">
                    <h3 class="mb-3"><i class="fas fa-unlock-alt me-2" style="color:#10B981;"></i> Decode & Reveal</h3>
                    <form method="POST" enctype="multipart/form-data">
                        <input type="hidden" name="action" value="decode_text">
                        <label class="form-label fw-semibold">Encoded Image</label>
                        <input type="file" name="image" class="form-control mb-3" accept="image/*" required>
                        
                        <div class="row g-2 mb-3">
                            <div class="col-md-5">
                                <select name="cipher" class="form-select">
                                    <option value="caesar">Caesar Cipher</option>
                                    <option value="vigenere">Vigenère Cipher</option>
                                </select>
                            </div>
                            <div class="col-md-7">
                                <input type="text" name="key" class="form-control" placeholder="Decryption key" required>
                            </div>
                        </div>
                        <button type="submit" class="btn btn-primary-gradient w-100">
                            <i class="fas fa-eye"></i> Decode & Decrypt
                        </button>
                    </form>
                    
                    {% if text_result %}
                    <div class="mt-4 result-box">
                        <div class="d-flex align-items-center gap-2 mb-2">
                            <i class="fas fa-comment-dots text-primary"></i>
                            <strong>Decoded Secret:</strong>
                        </div>
                        <p class="mb-0">{{ text_result }}</p>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
        {% else %}
        <!-- ==================== FILE STEGANOGRAPHY PAGE ==================== -->
        <div class="row g-4">
            <div class="col-lg-6">
                <div class="card-modern p-4 h-100">
                    <h3 class="mb-3"><i class="fas fa-folder-archive me-2" style="color:#F59E0B;"></i> Encode Any File</h3>
                    <form id="encodeFileForm" method="POST" enctype="multipart/form-data">
                        <input type="hidden" name="action" value="encode_file">
                        <input type="hidden" name="session_id" id="encodeSessionId" value="">
                        <label class="form-label fw-semibold">Cover Image (PNG/JPG)</label>
                        <input type="file" name="image" class="form-control mb-3" accept="image/*" required id="coverImageFileInput">
                        
                        <div id="imageFileCapacity" class="file-info mb-3" style="display: none;">
                            <i class="fas fa-database me-2"></i> <span id="capacityFileText">Calculating capacity...</span>
                        </div>
                        
                        <label class="form-label fw-semibold">Secret File (Max 50MB - PDF, ZIP, Images, etc.)</label>
                        <input type="file" name="secret_file" class="form-control mb-3" required id="secretFileInput">
                        
                        <div id="secretFileInfo" class="file-info mb-3" style="display: none;">
                            <i class="fas fa-file me-2"></i> File size: <span id="secretFileSize">0</span>
                        </div>
                        
                        <div id="capacityWarning" class="alert alert-warning mb-3" style="display: none;">
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            <span id="warningText"></span>
                        </div>
                        
                        <div class="progress-container" id="fileEncodeProgressContainer">
                            <div class="progress">
                                <div class="progress-bar" id="fileEncodeProgressBar" style="width: 0%"></div>
                            </div>
                            <div class="progress-text text-center" id="fileEncodeProgressText">Ready to encode</div>
                        </div>
                        
                        <button type="submit" id="encodeFileBtn" class="btn btn-primary-gradient w-100">
                            <i class="fas fa-compress-alt"></i> Encode & Download Stego Image
                        </button>
                    </form>
                </div>
            </div>
            
            <div class="col-lg-6">
                <div class="card-modern p-4 h-100">
                    <h3 class="mb-3"><i class="fas fa-folder-open me-2" style="color:#3B82F6;"></i> Extract Hidden File</h3>
                    <form id="decodeFileForm" method="POST" enctype="multipart/form-data">
                        <input type="hidden" name="action" value="decode_file">
                        <input type="hidden" name="session_id" id="decodeSessionId" value="">
                        <label class="form-label fw-semibold">Steganographic Image</label>
                        <input type="file" name="image" class="form-control mb-4" accept="image/*" required id="decodeFileInput">
                        
                        <div class="progress-container" id="fileDecodeProgressContainer">
                            <div class="progress">
                                <div class="progress-bar" id="fileDecodeProgressBar" style="width: 0%"></div>
                            </div>
                            <div class="progress-text text-center" id="fileDecodeProgressText">Ready to extract</div>
                        </div>
                        
                        <button type="submit" id="decodeFileBtn" class="btn btn-primary-gradient w-100 mt-3">
                            <i class="fas fa-download"></i> Extract & Download File
                        </button>
                    </form>
                    {% if file_result_msg %}
                    <div class="mt-4 result-box">
                        <i class="fas fa-check-circle text-success me-2"></i> {{ file_result_msg }}
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
        {% endif %}
    </div>
    <footer>
        <i class="fas fa-shield-alt me-1"></i> StegaVault • Military-grade steganography • Maximum file size: 50MB • LSB encryption • Supports all file types including PDFs
    </footer>
</div>

<script>
    let encodeEventSource = null;
    let decodeEventSource = null;
    
    // Helper function to update key placeholder
    function updateKeyPlaceholderText() {
        let cipher = document.getElementById("cipherSelectText");
        if (cipher) {
            let keyInput = document.getElementById("keyInputText");
            if(cipher.value === "caesar") keyInput.placeholder = "Numeric shift (e.g., 5)";
            else keyInput.placeholder = "Keyword (e.g., SECRET)";
        }
    }
    
    // Text encryption client-side
    function encryptClientText() {
        let message = document.querySelector('textarea[name="message"]').value;
        let cipher = document.getElementById("cipherSelectText").value;
        let key = document.getElementById("keyInputText").value;
        if(!message || !key) { alert("Please fill message and key"); return; }
        
        let result = "";
        if(cipher === "caesar") {
            let shift = parseInt(key);
            if(isNaN(shift)) { alert("Caesar needs numeric key"); return; }
            for(let ch of message) {
                if(/[a-zA-Z]/.test(ch)) {
                    let base = ch === ch.toUpperCase() ? 65 : 97;
                    result += String.fromCharCode((ch.charCodeAt(0) - base + shift) % 26 + base);
                } else result += ch;
            }
        } else if(cipher === "vigenere") {
            let keyLower = key.toLowerCase();
            let j = 0;
            for(let ch of message) {
                if(/[a-zA-Z]/.test(ch)) {
                    let shift = keyLower.charCodeAt(j % keyLower.length) - 97;
                    let base = ch === ch.toUpperCase() ? 65 : 97;
                    result += String.fromCharCode((ch.charCodeAt(0) - base + shift) % 26 + base);
                    j++;
                } else result += ch;
            }
        }
        document.getElementById("encryptedResult").value = result;
        document.getElementById("finalEncryptedMsg").value = result;
    }
    
    // Generate session ID
    function generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    // Real progress tracking for encoding
    function startEncodeProgressTracking(sessionId) {
        if (encodeEventSource) {
            encodeEventSource.close();
        }
        
        encodeEventSource = new EventSource('/progress/' + sessionId);
        encodeEventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            if (data.encode !== undefined) {
                const progress = Math.floor(data.encode);
                document.getElementById('fileEncodeProgressBar').style.width = progress + '%';
                document.getElementById('fileEncodeProgressText').innerHTML = `Encoding: ${progress}%`;
                
                if (data.complete || progress >= 100) {
                    setTimeout(() => {
                        document.getElementById('fileEncodeProgressText').innerHTML = 'Complete! Downloading...';
                    }, 500);
                }
            }
        };
        
        encodeEventSource.onerror = function() {
            if (encodeEventSource) {
                encodeEventSource.close();
                encodeEventSource = null;
            }
        };
    }
    
    // Real progress tracking for decoding
    function startDecodeProgressTracking(sessionId) {
        if (decodeEventSource) {
            decodeEventSource.close();
        }
        
        decodeEventSource = new EventSource('/progress/' + sessionId);
        decodeEventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            if (data.decode !== undefined) {
                const progress = Math.floor(data.decode);
                document.getElementById('fileDecodeProgressBar').style.width = progress + '%';
                document.getElementById('fileDecodeProgressText').innerHTML = `Extracting: ${progress}%`;
                
                if (data.complete || progress >= 100) {
                    setTimeout(() => {
                        document.getElementById('fileDecodeProgressText').innerHTML = 'Complete! Downloading...';
                    }, 500);
                }
            }
        };
        
        decodeEventSource.onerror = function() {
            if (decodeEventSource) {
                decodeEventSource.close();
                decodeEventSource = null;
            }
        };
    }
    
    // Calculate image capacity for text
    document.getElementById('coverImageInput')?.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            const img = new Image();
            img.onload = function() {
                const capacityBytes = Math.floor((img.width * img.height * 3) / 8);
                const capacityKB = (capacityBytes / 1024).toFixed(2);
                document.getElementById('imageCapacity').style.display = 'block';
                document.getElementById('capacityText').innerHTML = `Maximum capacity: ${capacityKB} KB (${capacityBytes} bytes)`;
            };
            img.src = URL.createObjectURL(file);
        }
    });
    
    // Monitor message size
    document.getElementById('secretMessage')?.addEventListener('input', function(e) {
        const message = e.target.value;
        const size = new Blob([message]).size;
        document.getElementById('messageSize').style.display = 'block';
        document.getElementById('messageSizeText').innerHTML = size;
        
        // Check capacity
        const capacityText = document.getElementById('capacityText')?.innerText;
        if (capacityText) {
            const capacityMatch = capacityText.match(/(\d+) bytes/);
            if (capacityMatch && size > parseInt(capacityMatch[1])) {
                document.getElementById('messageSize').style.backgroundColor = '#fee';
                document.getElementById('messageSize').style.border = '1px solid #f00';
            } else if (capacityMatch) {
                document.getElementById('messageSize').style.backgroundColor = '#f8f9fa';
                document.getElementById('messageSize').style.border = 'none';
            }
        }
    });
    
    // File steganography - capacity check
    let currentCoverCapacity = 0;
    
    document.getElementById('coverImageFileInput')?.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            const img = new Image();
            img.onload = function() {
                currentCoverCapacity = Math.floor((img.width * img.height * 3) / 8);
                const capacityMB = (currentCoverCapacity / (1024 * 1024)).toFixed(2);
                document.getElementById('imageFileCapacity').style.display = 'block';
                document.getElementById('capacityFileText').innerHTML = `Maximum capacity: ${capacityMB} MB (${currentCoverCapacity.toLocaleString()} bytes)`;
                checkFileCapacity();
            };
            img.src = URL.createObjectURL(file);
        }
    });
    
    document.getElementById('secretFileInput')?.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
            document.getElementById('secretFileInfo').style.display = 'block';
            document.getElementById('secretFileSize').innerHTML = `${sizeMB} MB (${file.size.toLocaleString()} bytes)`;
            checkFileCapacity();
        }
    });
    
    function checkFileCapacity() {
        const secretFile = document.getElementById('secretFileInput').files[0];
        if (secretFile && currentCoverCapacity > 0) {
            const warningDiv = document.getElementById('capacityWarning');
            const warningText = document.getElementById('warningText');
            const encodeBtn = document.getElementById('encodeFileBtn');
            
            // Add 100 bytes for header overhead
            const requiredCapacity = secretFile.size + 100;
            
            if (requiredCapacity > currentCoverCapacity) {
                warningDiv.style.display = 'block';
                warningText.innerHTML = `⚠️ File size (${(secretFile.size / (1024 * 1024)).toFixed(2)} MB) exceeds image capacity (${(currentCoverCapacity / (1024 * 1024)).toFixed(2)} MB). Please use a larger image or smaller file.`;
                encodeBtn.disabled = true;
            } else {
                warningDiv.style.display = 'none';
                encodeBtn.disabled = false;
            }
        }
    }
    
    // Handle encode form submission with real progress
    document.getElementById('encodeFileForm')?.addEventListener('submit', function(e) {
        const sessionId = generateSessionId();
        document.getElementById('encodeSessionId').value = sessionId;
        document.getElementById('fileEncodeProgressContainer').style.display = 'block';
        document.getElementById('fileEncodeProgressBar').style.width = '0%';
        document.getElementById('fileEncodeProgressText').innerHTML = 'Starting encoding...';
        startEncodeProgressTracking(sessionId);
    });
    
    // Handle decode form submission with real progress
    document.getElementById('decodeFileForm')?.addEventListener('submit', function(e) {
        const sessionId = generateSessionId();
        document.getElementById('decodeSessionId').value = sessionId;
        document.getElementById('fileDecodeProgressContainer').style.display = 'block';
        document.getElementById('fileDecodeProgressBar').style.width = '0%';
        document.getElementById('fileDecodeProgressText').innerHTML = 'Starting extraction...';
        startDecodeProgressTracking(sessionId);
    });
    
    // Handle text form submission with simulated progress (since text encoding is fast)
    document.getElementById('encodeTextForm')?.addEventListener('submit', function() {
        document.getElementById('textProgressContainer').style.display = 'block';
        let progress = 0;
        const interval = setInterval(() => {
            progress += 20;
            if (progress >= 100) {
                progress = 100;
                clearInterval(interval);
            }
            document.getElementById('textProgressBar').style.width = progress + '%';
            document.getElementById('textProgressText').innerHTML = `Processing... ${progress}%`;
        }, 200);
    });
    
    // Initialize
    updateKeyPlaceholderText();
</script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    active_page = request.args.get("page", "text")
    text_result = None
    file_result_msg = None
    
    if request.method == "POST":
        action = request.form.get("action")
        session_id = request.form.get("session_id")
        
        # Initialize progress tracking for this session
        if session_id:
            progress_tracking[session_id] = {'encode': 0, 'decode': 0, 'timestamp': time.time()}
        
        # Check file size
        if request.files:
            for file_key, file in request.files.items():
                if file and hasattr(file, 'content_length') and file.content_length > MAX_FILE_SIZE:
                    return f"File size exceeds maximum limit of {MAX_FILE_SIZE / (1024 * 1024)} MB", 400
        
        # ---------- TEXT ENCODE ----------
        if action == "encode_text" and "encode_submit" in request.form:
            image_file = request.files.get("image")
            final_message = request.form.get("final_message") or request.form.get("message", "")
            if not image_file or not final_message:
                return "Missing image or message", 400
            
            img_path = os.path.join(UPLOAD_FOLDER, secure_filename(image_file.filename))
            image_file.save(img_path)
            
            encoded_path = encode_text_in_image(img_path, final_message)
            if encoded_path and os.path.exists(encoded_path):
                # Cleanup original image
                if os.path.exists(img_path):
                    os.remove(img_path)
                # Cleanup progress tracking
                if session_id and session_id in progress_tracking:
                    del progress_tracking[session_id]
                return send_file(encoded_path, as_attachment=True, download_name="stego_text_image.png")
            else:
                # Cleanup
                if os.path.exists(img_path):
                    os.remove(img_path)
                if session_id and session_id in progress_tracking:
                    del progress_tracking[session_id]
                return "❌ Message too large for this image capacity! Please use a larger image or smaller message.", 400
        
        # ---------- TEXT DECODE ----------
        elif action == "decode_text":
            image_file = request.files.get("image")
            cipher = request.form.get("cipher", "caesar")
            key = request.form.get("key", "")
            if not image_file or not key:
                return "Missing image or key", 400
            
            img_path = os.path.join(UPLOAD_FOLDER, secure_filename(image_file.filename))
            image_file.save(img_path)
            
            extracted_encrypted = decode_text_from_image(img_path)
            # Cleanup
            if os.path.exists(img_path):
                os.remove(img_path)
                
            if extracted_encrypted is None:
                text_result = "⚠️ No hidden message found or corrupted image."
            else:
                try:
                    if cipher == "caesar":
                        text_result = caesar_decrypt(extracted_encrypted, key)
                    else:
                        text_result = vigenere_decrypt(extracted_encrypted, key)
                except Exception as e:
                    text_result = f"Decryption error: {str(e)}"
        
        # ---------- FILE ENCODE ----------
        elif action == "encode_file":
            image = request.files.get("image")
            secret_file = request.files.get("secret_file")
            if not image or not secret_file:
                return "Missing image or secret file", 400
            
            # Check file size
            if secret_file.content_length > MAX_FILE_SIZE:
                return f"Secret file exceeds maximum size of {MAX_FILE_SIZE / (1024 * 1024)} MB", 400
            
            img_path = os.path.join(UPLOAD_FOLDER, secure_filename(image.filename))
            file_path = os.path.join(UPLOAD_FOLDER, secure_filename(secret_file.filename))
            image.save(img_path)
            secret_file.save(file_path)
            
            # Calculate capacity before encoding
            img_check = cv2.imread(img_path)
            if img_check is None:
                # Cleanup
                if os.path.exists(img_path):
                    os.remove(img_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                if session_id and session_id in progress_tracking:
                    del progress_tracking[session_id]
                return "Invalid image file", 400
            
            total_bits = img_check.shape[0] * img_check.shape[1] * 3
            capacity_bytes = total_bits // 8
            file_size = os.path.getsize(file_path)
            
            # Add header overhead (filename length + filename + file size)
            filename_bytes = secret_file.filename.encode('utf-8')
            header_overhead = 4 + len(filename_bytes) + 4  # 4 bytes for filename length, filename, 4 bytes for file size
            
            if file_size + header_overhead > capacity_bytes:
                # Cleanup
                if os.path.exists(img_path):
                    os.remove(img_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                if session_id and session_id in progress_tracking:
                    del progress_tracking[session_id]
                return f"❌ File size ({get_file_size_info(file_size)}) exceeds image capacity ({get_file_size_info(capacity_bytes)}). Please use a larger image or smaller file.", 400
            
            # Encode with progress tracking
            encoded_path = encode_file_in_image(img_path, file_path, session_id)
            
            # Cleanup progress tracking
            if session_id and session_id in progress_tracking:
                del progress_tracking[session_id]
            
            if encoded_path:
                # Cleanup temporary files
                if os.path.exists(img_path):
                    os.remove(img_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                return send_file(encoded_path, as_attachment=True, download_name="stego_file_encoded.png")
            else:
                # Cleanup
                if os.path.exists(img_path):
                    os.remove(img_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                return "❌ Failed to encode file. Please try again.", 400
        
        # ---------- FILE DECODE ----------
        elif action == "decode_file":
            image = request.files.get("image")
            if not image:
                return "Missing image", 400
            
            img_path = os.path.join(UPLOAD_FOLDER, secure_filename(image.filename))
            image.save(img_path)
            
            output_path, filename = decode_file_from_image(img_path, session_id)
            
            # Cleanup progress tracking
            if session_id and session_id in progress_tracking:
                del progress_tracking[session_id]
            
            # Cleanup the uploaded image
            if os.path.exists(img_path):
                os.remove(img_path)
                
            if output_path and os.path.exists(output_path):
                return send_file(output_path, as_attachment=True, download_name=filename)
            else:
                file_result_msg = "❌ No hidden file detected or invalid stego image."
    
    # Cleanup old temp files (older than 1 hour)
    try:
        current_time = time.time()
        for filename in os.listdir(UPLOAD_FOLDER):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath) and (current_time - os.path.getmtime(filepath)) > 3600:
                os.remove(filepath)
    except:
        pass  # Ignore cleanup errors
    
    return render_template_string(MASTER_TEMPLATE, active_page=active_page, text_result=text_result, file_result_msg=file_result_msg)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
