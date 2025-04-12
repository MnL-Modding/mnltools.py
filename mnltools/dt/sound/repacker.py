import argparse
import functools
import io
import os
import pathlib
import re
import struct
import sys
import typing

import mnllib


RECORD_ID_PATTERN = re.compile(r".+_(\d+)")


def repack_sound_data(
    sound_data: typing.BinaryIO | str | os.PathLike[str],
    bank_id: int,
    directory: str | os.PathLike[str],
    *,
    silent: bool = True,
) -> None:
    with mnllib.stream_or_open_file(sound_data, "r+b") as sound_data:
        while True:
            current_bank_id_data = sound_data.read(4)
            if current_bank_id_data == b"":
                raise LookupError(f"bank {bank_id} not found")
            if struct.unpack("<I", current_bank_id_data)[0] == bank_id:
                break
            sound_data.seek(0x4, os.SEEK_CUR)
            (next_bank_offset,) = struct.unpack("<I", sound_data.read(4))
            sound_data.seek(next_bank_offset - 0xC, os.SEEK_CUR)
        bank_offset = sound_data.tell() - 0x4
        record_count, next_bank_offset, data_start_offset = struct.unpack(
            "<III", sound_data.read(12)
        )
        sound_data.seek(0x10 + record_count * 16, os.SEEK_CUR)
        name_table = sound_data.read(data_start_offset - 0x20 - record_count * 16)
        name_table_io = io.BytesIO(name_table)
        filenames: list[str] = []
        for _ in range(record_count):
            (length,) = struct.unpack("<B", name_table_io.read(1))
            filenames.append(name_table_io.read(length)[:-1].decode())
        sound_data.seek(bank_offset + next_bank_offset)
        sound_data_remainder = bytearray(sound_data.read())

        new_records_header = bytearray()
        new_bank_data = bytearray()
        for file in filenames:
            if not silent:
                print(f"Packing {file}...", file=sys.stderr)
            if bank_id < 4:
                record_id_match = RECORD_ID_PATTERN.fullmatch(file)
                record_id = (
                    int(record_id_match.group(1)) if record_id_match is not None else 0
                )
            else:
                record_id = 0
            bank_data_len = len(new_bank_data)
            offset = 0x20 + record_count * 16 + len(name_table) + bank_data_len
            new_bank_data += pathlib.Path(directory, f"{file}.rsd").read_bytes()
            new_records_header += struct.pack(
                "<III4x", record_id, len(new_bank_data) - bank_data_len, offset
            )
        new_bank_data += b"\x00" * ((-len(new_bank_data)) % 4)
        if not silent:
            print("Saving file...", file=sys.stderr)
        sound_data.seek(bank_offset + 0x4)
        sound_data.write(
            struct.pack(
                "<III",
                record_count,
                0x20 + len(new_records_header) + len(name_table) + len(new_bank_data),
                0x20 + len(new_records_header) + len(name_table),
            )
        )
        sound_data.seek(0x10, os.SEEK_CUR)
        sound_data.write(new_records_header)
        sound_data.write(name_table)
        sound_data.write(new_bank_data)
        sound_data_remainder_offset = sound_data.tell()
        bank_offset = 0
        while bank_offset < len(sound_data_remainder):
            sound_data_remainder[bank_offset + 0x10 : bank_offset + 0x14] = struct.pack(
                "<I", sound_data_remainder_offset + bank_offset
            )
            bank_offset += struct.unpack_from(
                "<I", sound_data_remainder, offset=bank_offset + 0x8
            )[0]
        sound_data.write(sound_data_remainder)
        sound_data.truncate()


class DTSoundDataRepackerArguments(argparse.Namespace):
    sound_data: pathlib.Path
    bank: int
    directory: pathlib.Path
    quiet: bool


def main() -> None:
    argp = argparse.ArgumentParser(
        description="""
            Repacker for the SoundData.arc file
            used in Mario & Luigi: Dream Team (Bros.).
        """
    )
    argp.register("type", "int in any base", functools.partial(int, base=0))
    argp.add_argument(
        "sound_data", help="the SoundData.arc file to repack", type=pathlib.Path
    )
    argp.add_argument(
        "bank", help="the ID of the bank to repack", type="int in any base"
    )
    argp.add_argument(
        "directory",
        help="the directory containing the `.rsd` files to pack",
        type=pathlib.Path,
    )
    argp.add_argument(
        "-q", "--quiet", help="only print warnings and errors", action="store_true"
    )
    args = argp.parse_args(namespace=DTSoundDataRepackerArguments())

    repack_sound_data(args.sound_data, args.bank, args.directory, silent=args.quiet)


if __name__ == "__main__":
    main()
