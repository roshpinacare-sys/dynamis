import sys
import json
import hashlib

def compute_fingerprint(file_path):
    sha256_hash = hashlib.sha256()
    byte_count = 0
    newline_count = 0
    file_type = "text"
    
    with open(file_path, 'rb') as f:
        # Read the file in chunks to handle large files efficiently
        chunk_size = 8192
        first_chunk = True
        first_512_bytes = b''
        
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            
            # Update hash and byte count
            sha256_hash.update(chunk)
            byte_count += len(chunk)
            
            # Count newlines
            newline_count += chunk.count(b'\n')
            
            # Store the first 512 bytes for type detection
            if first_chunk:
                first_512_bytes = chunk[:512]
                first_chunk = False
        
        # Determine file type
        if not first_512_bytes:
            file_type = "text"  # Empty file is considered text
        elif first_512_bytes[0:1] in [b'{', b'[']:
            file_type = "json"
        else:
            # Check if all first 512 bytes are text-like
            is_text = True
            for byte in first_512_bytes:
                if not (byte in [9, 10, 13, 12] or (32 <= byte <= 126)):
                    is_text = False
                    break
            file_type = "text" if is_text else "binary"
    
    # Calculate line count
    if byte_count == 0:
        line_count = 0
    else:
        line_count = newline_count
        if first_512_bytes and first_512_bytes[-1:] != b'\n':
            line_count += 1
    
    # Prepare the result
    result = {
        "sha256": sha256_hash.hexdigest(),
        "bytes": byte_count,
        "lines": line_count,
        "type": file_type
    }
    
    return json.dumps(result)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python main.py <file_path>"}))
        sys.exit(1)
    
    file_path = sys.argv[1]
    try:
        fingerprint = compute_fingerprint(file_path)
        print(fingerprint)
    except Exception as e:
        error_result = {"error": str(e)}
        print(json.dumps(error_result))
        sys.exit(1)
