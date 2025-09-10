````markdown
# tinygrep

Small grep-like CLI with a tiny regex engine.

---

## Install (local/GitHub)

Pick one.

### pipx (recommended)
```bash
# install directly from your GitHub repo
pipx install "git+https://github.com/TomOst-Sec/tinygrep.git"
# upgrade later
pipx upgrade tinygrep
# uninstall
pipx uninstall tinygrep
````

### pip (project venv)

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "git+https://github.com/TomOst-Sec/tinygrep.git"
# uninstall:  python -m pip uninstall tinygrep
```

### From a local clone

```bash
git clone https://github.com/TomOst-Sec/tinygrep.git
cd tinygrep
# option A: isolated app install
pipx install .
# option B: editable dev install
python -m venv .venv && source .venv/bin/activate
python -m pip install -e .
```

---

## Usage

```bash
tinygrep -E <pattern> [FILE...]
cat file.txt | tinygrep -E <pattern>
tinygrep -r -E <pattern> <dir>
```

Exit code is `0` if any line matched, else `1`. With `-r`, file paths are prefixed.

---

## Regex features

* Literals and dot: `.`
* Classes: `[abc]`, `[^abc]`, `\d`, `\w` (includes `_`)
* Groups and backrefs: `( … )`, `\1`, `\2`, …
* Alternation: `A|B`
* Quantifiers: `+`, `?`
* Anchors: `^`, `$`

Not supported yet: `*`, `{m,n}`, lookaround, flags.

---

## Quick tutorial

```bash
mkdir -p dir/subdir
printf "orange\npear\n" > dir/fruits-8790.txt
printf "cabbage\ncelery\ncauliflower\n" > dir/subdir/vegetables-9209.txt
printf "corn\nspinach\ncucumber\n" > dir/vegetables-7316.txt

tinygrep -r -E '.+er' dir/
# dir/vegetables-7316.txt:cucumber
# dir/subdir/vegetables-9209.txt:celery
# dir/subdir/vegetables-9209.txt:cauliflower
```

---

## Examples

### Multiple files

```bash
printf "orange\nlemon\n" > fruits-9153.txt
printf "zucchini\nspinach\n" > vegetables-4914.txt

tinygrep -E 'or.+$' fruits-9153.txt vegetables-4914.txt
# fruits-9153.txt:orange
```

### Backreferences (nested)

```bash
echo -n "'cat and cat' is the same as 'cat and cat'" \
| tinygrep -E "('(cat) and \2') is the same as \1"
# 'cat and cat' is the same as 'cat and cat'

echo -n "grep 101 is doing grep 101 times, and again grep 101 times" \
| tinygrep -E "((\w\w\w\w) (\d\d\d)) is doing \2 \3 times, and again \1 times"
# grep 101 is doing grep 101 times, and again grep 101 times
```

### Alternation + captures

```bash
echo -n "cat and fish, cat with fish" \
| tinygrep -E "(c.t|d.g) and (f..h|b..d), \1 with \2"
# cat and fish, cat with fish
```

### Quantifiers and optional

```bash
echo -n "howwdy hey there" \
| tinygrep -E "(how+dy) (he?y) there"
# howwdy hey there
```

### Wildcard

```bash
echo -n "cat" | tinygrep -E "c.t"
# cat
```

### Anchors

```bash
echo -n "strawberry_orange" | tinygrep -E "orange$"
# strawberry_orange

echo -n "pear" | tinygrep -E "^pear$"
# pear
```

### Character classes

```bash
echo -n "sally has 3 apples" | tinygrep -E "\d apple"
# sally has 3 apples

echo -n "abc-def is abc-def, not efg" \
| tinygrep -E "([abc]+)-([def]+) is \1-\2, not [^xyz]+"
# abc-def is abc-def, not efg
```

---

## Dev tips

```bash
# run tests like the examples above
tinygrep -E "ana$" <<<'banana'     # banana
tinygrep -E "(cat) and \1" <<<'cat and cat'
```

---

## License

MIT

```
```
