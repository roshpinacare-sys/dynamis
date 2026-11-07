import sys
import json
import hashlib

def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    
    target_path = sys.argv[1]
    
    try:
        with open(target_path, 'rb') as f:
            file_bytes = f.read()
    except FileNotFoundError:
        sys.exit(1)
    except IOError:
        sys.exit(1)

    # Calculate SHA256
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    # Calculate byte size
    byte_size = len(file_bytes)

    # Calculate line count
    line_count = 0
    if byte_size > 0:
        line_count = file_bytes.count(b'\n')
        if file_bytes[-1] != ord('\n'):
            line_count += 1
    else:
        line_count = 0

    # Determine type
    file_type = "text"
    if byte_size == 0:
        file_type = "text"
    else:
        first_byte = file_bytes[0]
        if first_byte == ord('{') or first_byte == ord('['):
            file_type = "json"
        else:
            # Check first 512 bytes for non-textual characters
            check_bytes = file_bytes[:512]
            is_text = True
            for byte_val in check_bytes:
                if not (byte_val in (9, 10, 13, 12) or (32 <= byte_val <= 126)):
                    is_text = False
                    break
            
            if not is_text:
                file_type = "binary"

    # Prepare and print the result
    result = {
        "sha256": sha256_hash,
        "bytes": byte_size,
        "lines": line_count,
        "type": file_type
    }
    
    print(json.dumps(result))

if __name__ == "__main__":
    main()
