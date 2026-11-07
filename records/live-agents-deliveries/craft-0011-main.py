import sys
import hashlib
import json

def determine_file_type(file_bytes):
    if not file_bytes:
        return "text"
    
    first_byte = file_bytes[0]
    if first_byte == ord('{') or first_byte == ord('['):
        return "json"
    
    if len(file_bytes) > 512:
        sample = file_bytes[:512]
    else:
        sample = file_bytes
        
    for byte in sample:
        if byte not in [9, 10, 13, 32, 127] and not (32 < byte < 127):
            return "binary"
            
    return "text"

def main():
    if len(sys.argv) < 2:
        print(json.dumps({}))
        return

    file_path = sys.argv[1]
    sha256_hash = hashlib.sha256()
    byte_count = 0
    line_count = 0
    ends_with_newline = False
    
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                
                sha256_hash.update(chunk)
                byte_count += len(chunk)
                
                for byte in chunk:
                    if byte == 10: # newline
                        line_count += 1
                        ends_with_newline = True
                    else:
                        if ends_with_newline:
                            # A non-newline byte after a newline means a new line started
                            line_count += 1
                            ends_with_newline = False
                        # else: we are in the middle of a line, do nothing
            # After the loop, check if the last byte was a newline
            # If the file is empty, line_count is 0. If it ends in a newline, line_count is correct.
            # If it does NOT end in a newline, we need to add 1 for the last line.
            if byte_count > 0 and not ends_with_newline:
                line_count += 1
            elif byte_count == 0:
                line_count = 0

    except FileNotFoundError:
        print(json.dumps({}))
        return
    except Exception:
        print(json.dumps({}))
        return

    file_bytes = sha256_hash.digest()
    file_type = determine_file_type(file_bytes)

    result = {
        "sha256": sha256_hash.hexdigest(),
        "bytes": byte_count,
        "lines": line_count,
        "type": file_type
    }
    
    print(json.dumps(result))

if __name__ == "__main__":
    main()
