import argparse
import math
import os
import pathlib
import shutil
import struct
import sys
import typing

import mnllib


BYTES_PER_FRAME = 8
SAMPLES_PER_FRAME = 14
NIBBLES_PER_FRAME = BYTES_PER_FRAME * 2

DEFAULT_EXTRA_LOOP_SAMPLES = 0x34004  # We use more to be safe but 212268 should work?


def nibble_to_sample(nibble: int) -> int:
    frames, extra_nibbles = divmod(nibble, NIBBLES_PER_FRAME)
    samples = SAMPLES_PER_FRAME * frames
    return samples + extra_nibbles - 2


def sample_to_nibble(sample: int) -> int:
    frames, extra_samples = divmod(sample, SAMPLES_PER_FRAME)
    return NIBBLES_PER_FRAME * frames + extra_samples + 2


def dsp_to_rsd(
    input: typing.BinaryIO | str | os.PathLike[str],
    output: typing.BinaryIO | str | os.PathLike[str],
    extra_loop_samples: int = DEFAULT_EXTRA_LOOP_SAMPLES,
    *,
    silent: bool = True,
) -> None:
    extra_loop_bytes = sample_to_nibble(extra_loop_samples)

    with mnllib.stream_or_open_file(input, "rb") as input:
        (
            sample_count,
            _nibble_count,
            sample_rate,
            looping,
            fmt,
            start_address,
            end_address,
            _current_address,
        ) = struct.unpack(">IIIHHIII", input.read(0x1C))
        if fmt != 0:
            raise ValueError(f"the input is not in ADPCM, but rather format {fmt}")
        if looping != 0:
            loop_start_sample = nibble_to_sample(start_address)
            loop_end_sample = nibble_to_sample(end_address)
            if not silent:
                print(
                    "INFO: The audio loops "
                    f"from {loop_start_sample} to {loop_end_sample}.",
                    file=sys.stderr,
                )
        elif not silent:
            print("INFO: The input has no loop points.", file=sys.stderr)
        input.seek(0x4A)
        channel_count, frames_per_interleave = struct.unpack(">HH", input.read(4))
        if frames_per_interleave != 1:
            raise ValueError(
                f"frames per interleave is not 1, but rather {frames_per_interleave} "
                "(if using VGAudio, make sure to use the RedSpark branch of the fork)"
            )
        if channel_count == 0:
            channel_count = 1
        coefs: list[tuple[int, ...]] = []
        for i in range(channel_count):
            input.seek(0x1C + i * 0x60)
            coefs.append(struct.unpack(">16HH3H3H", input.read(0x2E)))
        input.seek(0, os.SEEK_END)
        audio_size = input.tell() - 0x60 * channel_count + extra_loop_bytes

        with mnllib.stream_or_open_file(output, "wb") as output:
            output_position = 0
            output_position += output.write(
                struct.pack(
                    "<8sIIIIIHHI12x",
                    b"RedSpark",
                    0x1000 + audio_size,  # chunk size
                    0x00010000,  # type/chunk?
                    0x0000012C,  # ?
                    0,  # file id
                    0x1000,  # data offset
                    0,  # bank flag
                    0x0909,  # stream
                    0x1000 + audio_size,  # data size
                )
            )
            output_position += output.write(
                struct.pack(
                    "<I4x4xIII4x2xBBBB2x",
                    audio_size,  # data size
                    sample_rate,  # sample rate
                    sample_count,  # samples
                    0x0000C000,  # some chunk?
                    channel_count,  # channels
                    looping * 2,  # num loop cues
                    looping * 2,  # cues again?
                    0x7F,  # volume?
                )
            )
            for i in range(channel_count):
                output_position += output.write(
                    # config per channel (number/panning/volume/etc?)
                    struct.pack("<Q", 0x000000007F008000 + i)
                )
            if looping != 0:
                output_position += output.write(
                    struct.pack(
                        "<IIII",
                        0,  # chunk size?
                        loop_start_sample,  # value # pyright: ignore[reportPossiblyUnboundVariable] # noqa: E501
                        1,  # chunk size?
                        loop_end_sample,  # value # pyright: ignore[reportPossiblyUnboundVariable] # noqa: E501
                    )
                )
            for c in coefs:
                output_position += output.write(struct.pack("<16HH3H3H", *c))
            if looping != 0:
                output_position += output.write(
                    struct.pack(
                        "<I4x",
                        math.ceil(
                            loop_end_sample  # pyright: ignore[reportPossiblyUnboundVariable] # noqa: E501
                            / 12
                        )
                        * 12,  # offset?
                    )
                )
                for s in [b"Loop Start", b"Loop End"]:
                    output_position += output.write(struct.pack("<B", len(s)) + s)

            input.seek(0x60 * channel_count)
            output.write(b"\x00" * (0x1000 - output_position))
            shutil.copyfileobj(input, output)
            if looping != 0:
                input.seek(
                    0x60 * channel_count
                    + round(start_address / BYTES_PER_FRAME) * BYTES_PER_FRAME
                )
                output.write(input.read(extra_loop_bytes))


class DSP2RSDArguments(argparse.Namespace):
    input: pathlib.Path
    output: pathlib.Path | None
    quiet: bool
    extra_loop_samples: int


def main() -> None:
    argp = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Converter from DSP to streamed RSD (RedSpark) audio.\n\n"
        "The DSP must use exactly 1 frame per interleave "
        f"({SAMPLES_PER_FRAME} samples per interleave). "
        "One way to get such a file is to use the RedSpark branch of the VGAudio fork: "
        "https://github.com/MnL-Modding/VGAudio/releases",
    )
    argp.add_argument("input", help="the DSP file to convert", type=pathlib.Path)
    argp.add_argument(
        "-o",
        "--output",
        help="""
            the output RSD file
            (default is the input file with the extension `.rsd`,
            or STDOUT if the input is STDIN)
        """,
        type=pathlib.Path,
    )
    argp.add_argument(
        "-q", "--quiet", help="only print warnings and errors", action="store_true"
    )
    argp.add_argument(
        "-e",
        "--extra-loop-samples",
        help=f"""
            the number of extra samples to add to the end of the file when looping,
            in order to prevent noise (default: {DEFAULT_EXTRA_LOOP_SAMPLES})
        """,
        type=int,
        default=DEFAULT_EXTRA_LOOP_SAMPLES,
    )
    args = argp.parse_args(namespace=DSP2RSDArguments())

    input_stdin = str(args.input) == "-"
    if args.output is None:
        output = (
            args.input.with_suffix(".rsd") if not input_stdin else sys.stdout.buffer
        )
    elif str(args.output) == "-":
        output = sys.stdout.buffer
    else:
        output = args.output

    dsp_to_rsd(
        args.input if not input_stdin else sys.stdin.buffer,
        output,
        silent=args.quiet,
    )


if __name__ == "__main__":
    main()
