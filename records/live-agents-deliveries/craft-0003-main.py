import sys
import json
import hashlib

def main():
    if len(sys.argv) != 2:
        print(json.dumps({
            "sha256": "error",
            "bytes": -1,
            "lines": -1,
            "type": "error"
        }))
        return

    file_path = sys.argv[1]
    sha256_digest = ""
    byte_count = 0
    line_count = 0
    file_type = "binary"

    try:
        with open(file_path, 'rb') as f:
            # Read file in chunks to handle large files efficiently
            file_bytes = bytearray()
            for chunk in iter(lambda: f.read(4096), b""):
                file_bytes.extend(chunk)
            
            byte_count = len(file_bytes)

            # Calculate SHA256
            sha256_digest = hashlib.sha256(file_bytes).hexdigest()

            # Count lines
            line_count = 0
            if byte_count > 0:
                line_count = file_bytes.count(b'\n')
                if file_bytes[-1] != ord('\n'):
                    line_count += 1
            else:
                line_count = 0

            # Determine file type
            if byte_count == 0:
                file_type = "text" # Default for empty file
            else:
                first_byte = file_bytes[0]
                if first_byte == ord('{') or first_byte == ord('['):
                    file_type = "json"
                else:
                    # Check first 512 bytes for text criteria
                    check_length = min(512, byte_count)
                    is_text = True
                    for i in range(check_length):
                        byte_val = file_bytes[i]
                        # Check if byte is not printable ASCII, tab, newline, CR, or FF
                        if not (byte_val == 9 or byte_val == 10 or byte_val == 13 or 
                                byte_val == 12 or (32 <= byte_val <= 126)):
                            is_text = False
                            break
                    
                    if is_text:
                        file_type = "text"
                    else:
                        file_type = "binary"

    except Exception:
        # In case of any error (e.g., file not found), report error
        print(json.dumps({
            "sha256": "error",
            "bytes": -1,
            "lines": -1,
            "type": "error"
        }))
        return

    print(json.dumps({
        "sha256": sha256_digest,
        "bytes": byte_count,
        "lines": line_count,
        "type": file_type
    }))

if __name__ == "__main__":
    main()
