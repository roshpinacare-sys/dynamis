import sys
import json
import hashlib

def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python main.py <file_path>"}))
        return

    file_path = sys.argv[1]
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
    except FileNotFoundError:
        print(json.dumps({"error": f"File not found: {file_path}"}))
        return
    except IOError as e:
        print(json.dumps({"error": f"IO error reading file: {e}"}))
        return

    # Calculate sha256
    sha256_hash = hashlib.sha256(content).hexdigest()

    # Calculate byte size
    byte_size = len(content)

    # Calculate line count
    line_count = 0
    if byte_size > 0:
        line_count = content.count(b'\n')
        if not content.endswith(b'\n'):
            line_count += 1
    # else: line_count remains 0 for empty file

    # Determine type
    file_type = "binary"
    if byte_size == 0:
        file_type = "text"
    else:
        first_byte = content[0]
        if first_byte == ord('{') or first_byte == ord('['):
            file_type = "json"
        else:
            # Check first 512 bytes or all bytes if smaller
            check_bytes = content[:512]
            all_allowed = True
            for byte_val in check_bytes:
                if not (byte_val in {9, 10, 13, 12} or (32 <= byte_val <= 126)):
                    all_allowed = False
                    break
            if all_allowed:
                file_type = "text"

    result = {
        "sha256": sha256_hash,
        "bytes": byte_size,
        "lines": line_count,
        "type": file_type
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
