#!/usr/bin/env python3
import sys, string, os

# ------------------------------------------------------------
# Simple grep-like tool with a tiny custom regex engine.
#
# What you can write in patterns:
#   Literals:           a b c
#   Any char:           .
#   Char class:         [abc]      any of a,b,c
#   Negated class:      [^abc]     any char except a,b,c
#   Shorthand:          \d         digit 0-9
#                        \w         [0-9A-Za-z_]
#                        \\         a literal backslash
#   Grouping:           ( ... )
#   Alternation:        a|b|c
#   Quantifiers:        +  (one or more),  ?  (zero or one)
#   Anchors:            ^  start of string,  $  end of string
#   Backrefs:           \1 \2 ...  match exactly what group 1, 2, ... matched
#
# What this does NOT support (on purpose, to stay tiny):
#   '*'  '{m,n}'  lookaheads  lookbehinds  complex escapes  ranges like [a-z]
#
# Exit code:
#   0 if at least one match was printed, 1 if none, 1 for bad args.
#
# Modes:
#   -E <pattern>    provide the regex
#   file args       read files line-by-line and print matching lines
#   no files        read stdin line-by-line and print matching lines
#   -r dir ...      walk directories recursively and prefix "path:line"
# ------------------------------------------------------------

DIGITS = string.digits
WORD   = DIGITS + string.ascii_letters + "_"

# ---------------- regex engine ----------------
def find_close(p, i=0):
    """
    Find the index of the ')' that closes the '(' at or after position i.
    Skips over [...] character classes and respects escapes like '\]'.
    Raises ValueError if parentheses are unbalanced.

    Think: walk the pattern once, track:
      depth   -> how many '(' we've seen and not closed
      in_class-> are we inside a [...]
      esc     -> did we just see a backslash (so next char is literal)
    """
    depth=0; in_class=False; esc=False
    while i < len(p):
        c=p[i]
        if esc:
            esc=False
        elif c=="\\":
            esc=True
        elif in_class:
            if c=="]":
                in_class=False
        else:
            if c=="[":
                in_class=True
            elif c=="(":
                depth+=1
            elif c==")":
                depth-=1
                if depth==0:
                    return i
        i+=1
    raise ValueError("unbalanced ()")

def split_alts(p):
    """
    Split a pattern into top-level alternatives on '|' characters.
    Only splits when not inside (...) or [...] and not escaped.

    Example:
      "ab|(c|d)|e" -> ["ab", "(c|d)", "e"]
    """
    out=[]; start=0; depth=0; in_class=False; esc=False
    for i,c in enumerate(p):
        if esc: esc=False; continue
        if c=="\\": esc=True; continue
        if in_class:
            if c=="]": in_class=False
            continue
        if c=="[": in_class=True; continue
        if c=="(": depth+=1; continue
        if c==")": depth-=1; continue
        if c=="|" and depth==0:
            out.append(p[start:i]); start=i+1
    out.append(p[start:])
    return out

def count_groups(p):
    """
    Count how many '(' groups exist at any depth, ignoring [...] and escapes.
    Used to advance the global group numbering when we dive into a subpattern.
    """
    n=0; in_class=False; esc=False
    for c in p:
        if esc: esc=False; continue
        if c=="\\": esc=True; continue
        if in_class:
            if c=="]": in_class=False
            continue
        if c=="[": in_class=True; continue
        if c=="(": n+=1
    return n

def next_atom(p):
    """
    Parse the next *atom* from the pattern and return (predicate, rest).
    The predicate is a one-char test function f(ch)->bool.
    It handles '.', character classes, escapes like \d \w, and literals.

    If the pattern is empty, returns (None, "").
    """
    if not p: return None, ""
    if p[0] == ".":  # any char except newline
        return (lambda ch: ch != "\n"), p[1:]
    if p.startswith("[^]"):  # special case: anything at all
        return (lambda ch: True), p[3:]
    if p.startswith("[^"):
        # Negative class: collect explicit chars until ']'
        j=p.index("]"); bad=set(p[2:j])
        return (lambda ch,bad=bad: ch not in bad), p[j+1:]
    if p[0] == "[":
        # Positive class: any char in the set
        j=p.index("]"); good=set(p[1:j])
        return (lambda ch,good=good: ch in good), p[j+1:]
    if p[0] == "\\":
        # Escapes we support: \d, \w, and "\<char>" meaning literal <char>
        if len(p)<2: return (lambda ch: ch=="\\"), ""
        t=p[1]
        if   t=="d": return (lambda ch: ch in DIGITS), p[2:]
        elif t=="w": return (lambda ch: ch in WORD),   p[2:]
        else:        return (lambda ch,t=t: ch==t),    p[2:]
    # Literal single character
    c=p[0]; return (lambda ch,c=c: ch==c), p[1:]

def try_backref(s,p,caps):
    """
    If pattern at p starts with a backreference like \1 or \12:
      - Check the captured group string (caps is a list of group texts or None).
      - If that group exists and matches the front of s, consume it and return (new_s, new_p).
      - If the group exists but does not match, return False (a hard dead-end).
      - If no backref syntax is present at p, return None (no decision here).

    Backrefs use 1-based indexing like standard regexes.
    """
    if not p.startswith("\\") or len(p)<2 or not p[1].isdigit(): return None
    j=2
    while j<len(p) and p[j].isdigit(): j+=1
    idx=int(p[1:j])-1
    if idx<0 or idx>=len(caps) or caps[idx] is None: return False
    g=caps[idx]
    if not s.startswith(g): return False
    return s[len(g):], p[j:]

def gen(s,p,caps,gi):
    """
    Core backtracking matcher. Yields pairs (remaining_string, updated_captures)
    for every way the prefix of 's' can match the prefix of 'p'.

    Parameters:
      s   -> the part of the input we have not yet matched
      p   -> the part of the pattern we have not yet matched
      caps-> list of captured group texts (by index). Entries may be None.
      gi  -> next group index to assign for '(' we see here

    Strategy:
      - If we hit end of pattern, yield success (whatever is left of 's').
      - If pattern is a backreference, try to match that exact captured text.
      - If we see a '(' group:
          • find its ')'
          • for each top-level alternative inside, try to match it
          • record the substring that group consumed into caps[this_id]
          • handle quantifiers '+', '?' applied to the group as a unit
      - Otherwise read a single-char atom and honor '+', '?' on it.

    This is small, explicit backtracking. No DFA construction. Readable over fast.
    """
    if p == "":
        yield s, caps; return

    # 1) Backreference check (\1, \2, ...)
    br = try_backref(s,p,caps)
    if br is False: return
    if br is not None:
        s2, p2 = br
        yield from gen(s2,p2,caps,gi); return

    # 2) Group handling: ( ... ) with optional + or ? after it
    if p[0] == "(":
        j = find_close(p,0)
        body, rest = p[1:j], p[j+1:]
        q = rest[0] if rest else ""   # quantifier after the group if any
        this_id = gi                  # id for this '('
        inner_start = gi + 1          # groups inside start after this one
        span = 1 + count_groups(body) # how many ids we consume total

        def gen_body(s0, caps0):
            """
            Try each alternative inside the group on s0.
            On success, set caps[this_id] to the substring that matched the group.
            """
            for alt in split_alts(body):
                # Ensure caps list is long enough
                cc = caps0[:] + [None]*max(0,this_id+1-len(caps0))
                for out_s, cc2 in gen(s0, alt, cc, inner_start):
                    cc3 = cc2[:] + [None]*max(0,this_id+1-len(cc2))
                    # The group's text is what we consumed from s0
                    cc3[this_id] = s0[:len(s0)-len(out_s)]
                    yield out_s, cc3

        if q == "+":
            # One or more repetitions of the whole group.
            rest2 = rest[1:]
            # Seed with one match of the body; then keep stacking more.
            stack = list(gen_body(s, caps))
            while stack:
                out_s, ccx = stack.pop()
                # After k repetitions, try to match the rest of the pattern.
                yield from gen(out_s, rest2, ccx, gi + span)
                # If we consumed at least one char, try to grow to k+1 reps.
                if len(out_s) < len(s):
                    for out2, cc2 in gen_body(out_s, ccx):
                        if len(out2) != len(out_s):
                            stack.append((out2, cc2))
            return

        if q == "?":
            # Zero or one repetition of the whole group.
            rest2 = rest[1:]
            for out_s, ccx in gen_body(s, caps):
                yield from gen(out_s, rest2, ccx, gi + span)
            # Also try skipping the group entirely.
            yield from gen(s, rest2, caps[:], gi + span)
            return

        # No quantifier: exactly one occurrence of the group.
        for out_s, ccx in gen_body(s, caps):
            yield from gen(out_s, rest, ccx, gi + span)
        return

    # 3) Single-character atom with optional + or ?
    f, rest = next_atom(p)
    if f is None: return
    q = rest[0] if rest else ""

    if q == "+":
        # One or more of this atom.
        tail = rest[1:]
        if not s or not f(s[0]): return
        # Find the maximal run of matching chars, then backtrack downwards.
        i=1
        while i<=len(s) and f(s[i-1]): i+=1
        i-=1
        for k in range(i,0,-1):
            yield from gen(s[k:], tail, caps[:], gi)
        return

    if q == "?":
        # Zero or one of this atom.
        tail = rest[1:]
        if s and f(s[0]): yield from gen(s[1:], tail, caps[:], gi)
        yield from gen(s, tail, caps[:], gi)
        return

    # Exactly one char must match.
    if not s or not f(s[0]): return
    yield from gen(s[1:], rest, caps, gi)

def matches(s,p):
    """
    High-level entry: does string s match pattern p somewhere?
    Implements grep-like behavior:
      - If ^...$ then require full-string match.
      - If ...$ then require match that ends at end of s.
      - If ^... then require match that starts at start of s.
      - Else search anywhere in the string.
    Also supports top-level alternation with split_alts.
    """
    alts = split_alts(p)
    if len(alts) > 1:
        return any(matches(s,a) for a in alts)
    if p.startswith("^") and p.endswith("$"):
        return any(out=="" for out,_ in gen(s,p[1:-1],[],0))
    if p.endswith("$"):
        core=p[:-1]
        for i in range(len(s)+1):
            if any(out=="" for out,_ in gen(s[i:],core,[],0)): return True
        return False
    if p.startswith("^"):
        return any(True for _ in gen(s,p[1:],[],0))
    for i in range(len(s)+1):
        if any(True for _ in gen(s[i:],p,[],0)): return True
    return False
# --------------- end regex engine ---------------

def _emit(s):
    """Write one line to stdout with a trailing newline. No buffering surprises."""
    os.write(1, (s + "\n").encode("utf-8"))

def _process_lines(lines, pat, prefix=""):
    """
    Given a list of text lines and a pattern, print each matching line.
    If prefix is non-empty, print 'prefix+line'.
    Returns True if at least one line matched.
    """
    matched = False
    for line in lines:
        if matches(line, pat):
            _emit((prefix + line) if prefix else line)
            matched = True
    return matched

def _process_file(path, pat, prefix=""):
    """
    Open a file safely, read all lines, and feed them to _process_lines.
    Returns True if any line matched. On any I/O error, returns False.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
    except Exception:
        return False
    return _process_lines(lines, pat, prefix)

def _walk_dir(base_dir, pat):
    """
    Recursively walk a directory tree.
    For each file, print 'normalized_path:line' on matches.
    Returns True if at least one line in the whole tree matched.
    """
    any_match = False
    base_norm = os.path.normpath(base_dir)
    for root, _, files in os.walk(base_dir):
        for name in files:
            full = os.path.join(root, name)
            rel  = os.path.relpath(full, start=base_dir)
            shown = os.path.normpath(os.path.join(base_norm, rel))
            if _process_file(full, pat, prefix=f"{shown}:"):
                any_match = True
    return any_match

def main():
    """
    CLI parser. Accepts flags in any order.

    Usage examples:
      echo "apple pie" | prog -E "apple"
      prog -E "cat$" file1.txt file2.txt
      prog -r -E ".+berry" dir/

    Behavior:
      - If -r is set, treat each path as file or directory and walk directories.
      - If no -r and paths are given, scan those files.
      - If no paths, read from stdin.
      - Exit 0 if any match printed. Exit 1 otherwise. Exit 1 on bad args.
    """
    args = sys.argv[1:]
    if not args:
        sys.exit(1)

    # parse flags in any order
    recurse = False
    pat = None
    paths = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-r":
            recurse = True
            i += 1
        elif a == "-E":
            if i + 1 >= len(args): sys.exit(1)
            pat = args[i + 1]
            i += 2
        else:
            paths.append(a)
            i += 1

    if pat is None:
        sys.exit(1)

    if recurse:
        if not paths: sys.exit(1)
        any_match = False
        for p in paths:
            if os.path.isdir(p):
                any_match |= _walk_dir(p, pat)
            elif os.path.isfile(p):
                any_match |= _process_file(p, pat, prefix=f"{os.path.normpath(p)}:")
        sys.exit(0 if any_match else 1)

    if paths:
        multi = len(paths) > 1
        any_match = False
        for fp in paths:
            pref = f"{fp}:" if multi else ""
            any_match |= _process_file(fp, pat, pref)
        sys.exit(0 if any_match else 1)

    # No paths -> read from stdin as a single virtual file
    txt = sys.stdin.read()
    ok = _process_lines(txt.splitlines(), pat)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
