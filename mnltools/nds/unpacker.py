import argparse
import os
import pathlib
import sys
import typing

import mnllib
import mnllib.nds
import ndspy.code
import ndspy.codeCompression
import ndspy.fnt
import ndspy.rom


def unpack_header_files(
    data_dir: pathlib.Path, rom: ndspy.rom.NintendoDSRom, header: bytes
) -> None:
    (data_dir / mnllib.nds.HEADER_PATH).write_bytes(header)
    ndspy.codeCompression.decompressToFile(  # pyright: ignore[reportUnknownMemberType]
        rom.arm9, data_dir / mnllib.nds.DECOMPRESSED_ARM9_PATH
    )
    (data_dir / mnllib.nds.ARM9_POST_DATA_PATH).write_bytes(rom.arm9PostData)
    (data_dir / mnllib.nds.ARM7_PATH).write_bytes(rom.arm7)
    (data_dir / mnllib.nds.ARM9_OVERLAY_TABLE_PATH).write_bytes(rom.arm9OverlayTable)
    (data_dir / mnllib.nds.ARM7_OVERLAY_TABLE_PATH).write_bytes(rom.arm7OverlayTable)
    (data_dir / mnllib.nds.BANNER_PATH).write_bytes(rom.iconBanner)


def unpack_overlays(
    data_dir: pathlib.Path, overlays: dict[int, ndspy.code.Overlay]
) -> None:
    (data_dir / mnllib.nds.DECOMPRESSED_OVERLAYS_DIR).mkdir(exist_ok=True)

    for i, overlay in overlays.items():
        mnllib.nds.fs_std_overlay_path(i, data_dir=data_dir).write_bytes(overlay.data)


def unpack_data_folder(
    files: list[bytes], folder: ndspy.fnt.Folder, path: pathlib.Path
) -> None:
    path.mkdir(exist_ok=True)

    for i, filename in enumerate(folder.files):
        (path / filename).write_bytes(files[folder.firstID + i])

    for subfolder_name, subfolder in folder.folders:
        unpack_data_folder(files, subfolder, path / subfolder_name)


def unpack_rom(
    data_dir: pathlib.Path, rom: ndspy.rom.NintendoDSRom, header: bytes
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)

    unpack_header_files(data_dir, rom, header)
    unpack_overlays(data_dir, rom.loadArm9Overlays())
    unpack_data_folder(rom.files, rom.filenames, data_dir / mnllib.nds.DATA_DIR)


def unpack_rom_from_file(
    data_dir: pathlib.Path, file: typing.BinaryIO | str | os.PathLike[str]
) -> None:
    with mnllib.stream_or_open_file(file, "rb") as file:
        header = file.read(0x200)
        rom = ndspy.rom.NintendoDSRom(header + file.read())

    unpack_rom(data_dir, rom, header)


class NDSUnpackerArguments(argparse.Namespace):
    rom: pathlib.Path
    data_dir: pathlib.Path
    quiet: bool


def main() -> None:
    argp = argparse.ArgumentParser(
        description="Unpacker for NDS ROMs into the mnllib standard."
    )
    argp.add_argument("rom", help="the ROM to unpack", type=pathlib.Path)
    argp.add_argument(
        "-d",
        "--data-dir",
        help=f"""
            the directory to unpack to
            (default: '{mnllib.DEFAULT_DATA_DIR_PATH}')
        """,
        type=pathlib.Path,
        default=mnllib.DEFAULT_DATA_DIR_PATH,
    )
    argp.add_argument(
        "-q", "--quiet", help="only print warnings and errors", action="store_true"
    )
    args = argp.parse_args(namespace=NDSUnpackerArguments())

    unpack_rom_from_file(
        args.data_dir, args.rom if str(args.rom) != "-" else sys.stdin.buffer
    )


if __name__ == "__main__":
    main()
