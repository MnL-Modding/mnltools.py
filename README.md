# `mnltools.py`
Python tools for the Mario & Luigi games.


## Installation
```bash
pip3 install mnltools
```


## Tools
### Generic Nintendo DS Tools
#### `mnl-nds-unpack`
```
usage: mnl-nds-unpack [-h] [-d DATA_DIR] [-q] rom

Unpacker for NDS ROMs into the mnllib standard.

positional arguments:
  rom                   the ROM to unpack

options:
  -h, --help            show this help message and exit
  -d, --data-dir DATA_DIR
                        the directory to unpack to (default: 'data')
  -q, --quiet           only print warnings and errors
```

#### `mnl-nds-pack`
```
usage: mnl-nds-pack [-h] -o OUTPUT [-r REFERENCE_ROM] [-d DATA_DIR] [-q]

Packer for NDS ROMs from the mnllib standard.

options:
  -h, --help            show this help message and exit
  -o, --output OUTPUT   the ROM file to create
  -r, --reference-rom REFERENCE_ROM
                        an optional ROM to copy matching overlays from in
                        order to avoid having to compress them again. By
                        default, this is the output file if it is not STDOUT;
                        to disable this, set it to 'NONE'.
  -d, --data-dir DATA_DIR
                        the directory to pack (default: 'data')
  -q, --quiet           only print warnings and errors
```


### Tools for *Dream Team (Bros.)*
#### `dsp2rsd`
```
usage: dsp2rsd [-h] [-o OUTPUT] [-q] [-e EXTRA_LOOP_SAMPLES] input

Converter from DSP to streamed RSD (RedSpark) audio.

The DSP must use exactly 1 frame per interleave (14 samples per interleave). One way to get such a file is to use the RedSpark branch of the VGAudio fork: https://github.com/MnL-Modding/VGAudio/releases

positional arguments:
  input                 the DSP file to convert

options:
  -h, --help            show this help message and exit
  -o, --output OUTPUT   the output RSD file (default is the input file with
                        the extension `.rsd`, or STDOUT if the input is STDIN)
  -q, --quiet           only print warnings and errors
  -e, --extra-loop-samples EXTRA_LOOP_SAMPLES
                        the number of extra samples to add to the end of the
                        file when looping, in order to prevent noise (default:
                        212996)
```

#### `mnl-dt-sounddata-repack`
```
usage: mnl-dt-sounddata-repack [-h] [-q] sound_data bank directory

Repacker for the SoundData.arc file used in Mario & Luigi: Dream Team (Bros.).

positional arguments:
  sound_data   the SoundData.arc file to repack
  bank         the ID of the bank to repack
  directory    the directory containing the `.rsd` files to pack

options:
  -h, --help   show this help message and exit
  -q, --quiet  only print warnings and errors
```
