import sys
import json
import hashlib

def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "bytes": 0,
            "lines": 0,
            "type": "json"
        }))
        return

    filepath = sys.argv[1]

    try:
        with open(filepath, 'rb') as f:
            content_bytes = f.read()
    except FileNotFoundError:
        print(json.dumps({
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "bytes": 0,
            "lines": 0,
            "type": "json"
        }))
        return

    byte_count = len(content_bytes)

    line_count = 0
    if byte_count > 0:
        newline_count = content_bytes.count(b'\n')
        line_count = newline_count
        if content_bytes[-1] != ord('\n'):
            line_count += 1

    data_type = "text"
    if byte_count > 0:
        first_byte = content_bytes[0]
        if first_byte == ord('{') or first_byte == ord('['):
            data_type = "json"
        else:
            is_printable = True
            sample_bytes = content_bytes[:512]
            for byte_val in sample_bytes:
                if not (32 <= byte_val <= 126 or
                        byte_val in [ord('\t'), ord('\n'), ord('\r'), ord('\f')]):
                    is_printable = False
                    break
            if not is_printable:
                data_type = "binary"

    sha256_hash = hashlib.sha256(content_bytes).hexdigest()

    result = {
        "sha256": sha256_hash,
        "bytes": byte_count,
        "lines": line_count,
        "type": data_type
    }

    print(json.dumps(result))

if __name__ == "__main__":
    main()
