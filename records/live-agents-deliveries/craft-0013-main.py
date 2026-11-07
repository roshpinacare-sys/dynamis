import sys
import json
import hashlib

def get_file_type(file_bytes):
    if not file_bytes:
        return "text"
    
    first_byte = file_bytes[0]
    if first_byte == ord('{') or first_byte == ord('['):
        return "json"
    
    # Check first 512 bytes for text criteria
    for byte in file_bytes[:512]:
        if byte not in {
            9,    # tab
            10,   # newline
            13,   # carriage return
            12,   # form feed
            32,   # space
        } and (byte < 32 or byte > 126):
            return "binary"
    
    return "text"

def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "bytes": 0,
            "lines": 0,
            "type": "text"
        }))
        return

    file_path = sys.argv[1]
    
    try:
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
    except FileNotFoundError:
        # Fallback for non-existent file, treating as empty
        file_bytes = b""

    # Calculate SHA256
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    # Calculate byte size
    byte_size = len(file_bytes)

    # Calculate line count
    newline_count = file_bytes.count(b'\n')
    if file_bytes:
        lines = newline_count + (0 if file_bytes.endswith(b'\n') else 1)
    else:
        lines = 0

    # Determine file type
    file_type = get_file_type(file_bytes)

    # Prepare and print the JSON output
    result = {
        "sha256": sha256_hash,
        "bytes": byte_size,
        "lines": lines,
        "type": file_type
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
