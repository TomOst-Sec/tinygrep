# tinygrep
Small grep-like CLI with a tiny regex engine.

## Install
pipx install tinygrep

## Usage
tinygrep -E "cat$" file.txt
tinygrep -r -E ".+berry" dir/
