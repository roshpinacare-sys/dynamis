import sys
import hashlib
import json

def determine_type(file_bytes):
    if not file_bytes:
        return "text"
    
    first_byte = file_bytes[0]
    if first_byte == ord('{') or first_byte == ord('['):
        return "json"
    
    # Check the first 512 bytes
    check_bytes = file_bytes[:512]
    for byte in check_bytes:
        if byte not in (
            9,      # tab
            10,     # newline
            13,     # carriage return
            12,     # form feed
            32,     # space
            33,     # !
            34,     # "
            35,     # #
            36,     # $
            37,     # %
            38,     # &
            39,     # '
            40,     # (
            41,     # )
            42,     # *
            43,     # +
            44,     # ,
            45,     # -
            46,     # .
            47,     # /
            48,     # 0
            49,     # 1
            50,     # 2
            51,     # 3
            52,     # 4
            53,     # 5
            54,     # 6
            55,     # 7
            56,     # 8
            57,     # 9
            58,     # :
            59,     # ;
            60,     # <
            61,     # =
            62,     # >
            63,     # ?
            64,     # @
            65,     # A
            66,     # B
            67,     # C
            68,     # D
            69,     # E
            70,     # F
            71,     # G
            72,     # H
            73,     # I
            74,     # J
            75,     # K
            76,     # L
            77,     # M
            78,     # N
            79,     # O
            80,     # P
            81,     # Q
            82,     # R
            83,     # S
            84,     # T
            85,     # U
            86,     # V
            87,     # W
            88,     # X
            89,     # Y
            90,     # Z
            91,     # [
            92,     # \
            93,     # ]
            94,     # ^
            95,     # _
            96,     # `
            97,     # a
            98,     # b
            99,     # c
            100,    # d
            101,    # e
            102,    # f
            103,    # g
            104,    # h
            105,    # i
            106,    # j
            107,    # k
            108,    # l
            109,    # m
            110,    # n
            111,    # o
            112,    # p
            113,    # q
            114,    # r
            115,    # s
            116,    # t
            117,    # u
            118,    # v
            119,    # w
            120,    # x
            121,    # y
            122,    # z
            123,    # {
            124,    # |
            125,    # }
            126,    # ~
        ):
            return "binary"
    return "text"

def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python main.py <file_path>"}))
        sys.exit(1)

    file_path = sys.argv[1]

    try:
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
    except FileNotFoundError:
        print(json.dumps({"error": f"File not found: {file_path}"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    byte_count = len(file_bytes)
    
    line_count = 0
    if byte_count > 0:
        line_count = file_bytes.count(b'\n')
        if file_bytes[-1] != ord('\n'):
            line_count += 1
    
    file_type = determine_type(file_bytes)

    result = {
        "sha256": sha256_hash,
        "bytes": byte_count,
        "lines": line_count,
        "type": file_type
    }

    print(json.dumps(result))

if __name__ == "__main__":
    main()
