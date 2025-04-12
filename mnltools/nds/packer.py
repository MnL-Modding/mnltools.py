import argparse
import os
import pathlib
import struct
import sys
import typing

import mnllib
import mnllib.nds
import ndspy.code
import ndspy.codeCompression
import ndspy.fnt
import ndspy.rom
import tqdm


def pack_header_files(
    data_dir: pathlib.Path,
    output_rom: ndspy.rom.NintendoDSRom,
    reference_rom: ndspy.rom.NintendoDSRom | None = None,
) -> None:
    with (data_dir / mnllib.nds.HEADER_PATH).open("rb") as file:
        (
            output_rom.name,
            output_rom.idCode,
            output_rom.developerCode,
            output_rom.unitCode,
            output_rom.encryptionSeedSelect,
            output_rom.deviceCapacity,
            output_rom.pad015,
            output_rom.pad016,
            output_rom.pad017,
            output_rom.pad018,
            output_rom.pad019,
            output_rom.pad01A,
            output_rom.pad01B,
            output_rom.pad01C,
            output_rom.region,
            output_rom.version,
            output_rom.autostart,
            _arm9_offset,
            output_rom.arm9EntryAddress,
            output_rom.arm9RamAddress,
            _arm9_len,
            _arm7_offset,
            output_rom.arm7EntryAddress,
            output_rom.arm7RamAddress,
            _arm7_len,
        ) = struct.unpack("<12s4s2s14B8I", file.read(0x40))
        file.seek(0x060)
        (
            output_rom.normalCardControlRegisterSettings,
            output_rom.secureCardControlRegisterSettings,
            _icon_banner_offset,
            output_rom.secureAreaChecksum,
            output_rom.secureTransferDelay,
            output_rom.arm9CodeSettingsPointerAddress,
            output_rom.arm7CodeSettingsPointerAddress,
            output_rom.secureAreaDisable,
            _rom_size_or_rsa_sig_offset,
            _header_size,
            output_rom.pad088,
            output_rom.nintendoLogo,
        ) = struct.unpack("<3I2H2I8s2I56s156s", file.read(0xFC))
        file.seek(0x168)
        (
            output_rom.debugRomAddress,
            output_rom.pad16C,
        ) = struct.unpack("<I148s", file.read(0x98))
        output_rom.pad200 = file.read()

    decompressed_arm9 = (data_dir / mnllib.nds.DECOMPRESSED_ARM9_PATH).read_bytes()
    if (
        reference_rom is not None
        and decompressed_arm9 == ndspy.codeCompression.decompress(reference_rom.arm9)
    ):
        output_rom.arm9 = reference_rom.arm9
    else:
        output_rom.arm9 = ndspy.code.MainCodeFile(
            decompressed_arm9,
            output_rom.arm9RamAddress,
            output_rom.arm9CodeSettingsPointerAddress,
        ).save(compress=True)
    output_rom.arm9PostData = (data_dir / mnllib.nds.ARM9_POST_DATA_PATH).read_bytes()
    output_rom.arm7 = (data_dir / mnllib.nds.ARM7_PATH).read_bytes()
    output_rom.arm9OverlayTable = (
        data_dir / mnllib.nds.ARM9_OVERLAY_TABLE_PATH
    ).read_bytes()
    output_rom.arm7OverlayTable = (
        data_dir / mnllib.nds.ARM7_OVERLAY_TABLE_PATH
    ).read_bytes()
    output_rom.iconBanner = (data_dir / mnllib.nds.BANNER_PATH).read_bytes()


def pack_overlays(
    data_dir: pathlib.Path,
    output_rom: ndspy.rom.NintendoDSRom,
    reference_rom: ndspy.rom.NintendoDSRom | None = None,
    *,
    disable_progress: bool | None = False,
) -> None:
    if reference_rom is not None:
        reference_overlays = reference_rom.loadArm9Overlays()
    else:
        reference_overlays = None

    arm9_overlay_table = bytearray(output_rom.arm9OverlayTable)

    for index, (
        overlay_id,
        ram_address,
        ram_size,
        bss_size,
        static_init_start,
        static_init_end,
        file_id,
        compressed_size_flags,
    ) in enumerate(
        tqdm.tqdm(
            struct.iter_unpack("<8I", output_rom.arm9OverlayTable),
            total=len(output_rom.arm9OverlayTable) // 32,
            disable=disable_progress,
        )
    ):
        flags = compressed_size_flags >> 24
        compressed = flags & 0x01 != 0

        overlay_data = mnllib.nds.fs_std_overlay_path(
            overlay_id, data_dir=data_dir
        ).read_bytes()
        ram_size = len(overlay_data)

        if (
            compressed
            and reference_overlays is not None
            and overlay_id in reference_overlays
            and overlay_data == reference_overlays[overlay_id].data
        ):
            encoded_overlay_data = typing.cast(
                ndspy.rom.NintendoDSRom, reference_rom
            ).files[reference_overlays[overlay_id].fileID]
        else:
            if compressed:
                encoded_overlay_data = ndspy.codeCompression.compress(
                    overlay_data, isArm9=False
                )
            else:
                encoded_overlay_data = overlay_data

        file_id = len(output_rom.files)
        output_rom.files.append(encoded_overlay_data)

        arm9_overlay_table[index * 32 : (index + 1) * 32] = struct.pack(
            "<8I",
            overlay_id,
            ram_address,
            ram_size,
            bss_size,
            static_init_start,
            static_init_end,
            file_id,
            len(encoded_overlay_data) | (flags << 24),
        )

    output_rom.arm9OverlayTable = bytes(arm9_overlay_table)


def pack_data_folder(
    path: pathlib.Path, folder: ndspy.fnt.Folder, files: list[bytes]
) -> None:
    subfolders: list[pathlib.Path] = []
    subfiles: list[pathlib.Path] = []
    for subpath in path.iterdir():
        if subpath.is_dir():
            subfolders.append(subpath)
        elif subpath.is_file():
            subfiles.append(subpath)
    subfolders.sort()
    subfiles.sort()

    for file in subfiles:
        files.append(file.read_bytes())
        folder.files.append(file.name)

    for subfolder_path in subfolders:
        subfolder = ndspy.fnt.Folder(firstID=len(files))
        pack_data_folder(subfolder_path, subfolder, files)
        folder.folders.append((subfolder_path.name, subfolder))
    folder.folders.sort(key=lambda subfolder: subfolder[0].casefold())


def pack_rom(
    data_dir: pathlib.Path,
    reference_rom: ndspy.rom.NintendoDSRom | None = None,
    output_rom: ndspy.rom.NintendoDSRom | None = None,
    *,
    silent: bool = False,
) -> ndspy.rom.NintendoDSRom:
    if output_rom is None:
        output_rom = ndspy.rom.NintendoDSRom()
        output_rom.rsaSignature = b"\xff" * 0x88

    if not silent:
        print("Packing header...", file=sys.stderr)
    pack_header_files(data_dir, output_rom, reference_rom)
    if not silent:
        print("Compressing overlays...", file=sys.stderr)
    pack_overlays(data_dir, output_rom, reference_rom, disable_progress=silent)
    if not silent:
        print("Packing data...", file=sys.stderr)
    pack_data_folder(
        data_dir / mnllib.nds.DATA_DIR, output_rom.filenames, output_rom.files
    )

    return output_rom


def pack_rom_to_file(
    data_dir: pathlib.Path,
    file: typing.BinaryIO | str | os.PathLike[str],
    reference_rom: ndspy.rom.NintendoDSRom | None = None,
    output_rom: ndspy.rom.NintendoDSRom | None = None,
    *,
    silent: bool = False,
) -> None:
    output_rom = pack_rom(data_dir, reference_rom, output_rom, silent=silent)

    with mnllib.stream_or_open_file(file, "wb") as file:
        file.write(output_rom.save())


class NDSPackerArguments(argparse.Namespace):
    output: pathlib.Path
    reference_rom: pathlib.Path | None
    data_dir: pathlib.Path
    quiet: bool


def main() -> None:
    argp = argparse.ArgumentParser(
        description="Packer for NDS ROMs from the mnllib standard."
    )
    argp.add_argument(
        "-o",
        "--output",
        help="the ROM file to create",
        type=pathlib.Path,
        required=True,
    )
    argp.add_argument(
        "-r",
        "--reference-rom",
        help="""
            an optional ROM to copy matching overlays from in order to avoid
            having to compress them again. By default, this is the output file if
            it is not STDOUT; to disable this, set it to 'NONE'.
        """,
        type=pathlib.Path,
    )
    argp.add_argument(
        "-d",
        "--data-dir",
        help=f"""
            the directory to pack
            (default: '{mnllib.DEFAULT_DATA_DIR_PATH}')
        """,
        type=pathlib.Path,
        default=mnllib.DEFAULT_DATA_DIR_PATH,
    )
    argp.add_argument(
        "-q", "--quiet", help="only print warnings and errors", action="store_true"
    )
    args = argp.parse_args(namespace=NDSPackerArguments())

    output_stdout = str(args.output) == "-"
    if args.reference_rom is None:
        if not output_stdout:
            reference_rom_path = args.output
        else:
            reference_rom_path = None
    elif str(args.reference_rom) == "NONE":
        reference_rom_path = None
    else:
        reference_rom_path = args.reference_rom
    if reference_rom_path is not None:
        try:
            with mnllib.stream_or_open_file(
                (
                    reference_rom_path
                    if str(reference_rom_path) != "-"
                    else sys.stdin.buffer
                ),
                "rb",
            ) as file:
                reference_rom = ndspy.rom.NintendoDSRom(file.read())
        except Exception:
            if reference_rom_path == args.output:
                reference_rom = None
            else:
                raise
    else:
        reference_rom = None

    pack_rom_to_file(
        args.data_dir,
        args.output if not output_stdout else sys.stdout.buffer,
        reference_rom,
        silent=args.quiet,
    )


if __name__ == "__main__":
    main()
