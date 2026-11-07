import sys
import hashlib
import json

def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "sha256": "",
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
        print(json.dumps({
            "sha256": "",
            "bytes": 0,
            "lines": 0,
            "type": "text"
        }))
        return

    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    byte_count = len(file_bytes)

    # Calculate line count
    newline_count = file_bytes.count(b'\n')
    line_count = newline_count
    if byte_count > 0 and not file_bytes.endswith(b'\n'):
        line_count += 1

    # Determine type
    file_type = "text"
    if byte_count > 0:
        first_byte = file_bytes[0]
        if first_byte == ord('{') or first_byte == ord('['):
            file_type = "json"
        else:
            # Check first 512 bytes for non-text characters
            check_bytes = file_bytes[:512]
            for byte in check_bytes:
                if not (byte == ord('\t') or byte == ord('\n') or
                        byte == ord('\r') or byte == ord('\f') or
                        (byte >= 0x20 and byte <= 0x7E)):
                    file_type = "binary"
                    break

    result = {
        "sha256": sha256_hash,
        "bytes": byte_count,
        "lines": line_count,
        "type": file_type
    }

    print(json.dumps(result))

if __name__ == "__main__":
    main()
