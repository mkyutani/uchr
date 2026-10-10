# Unicode Tools (uchr)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Unicode](https://img.shields.io/badge/Unicode-multi--version-green.svg)](https://unicode.org/)
[![PyPI version](https://badge.fury.io/py/uchr.svg)](https://badge.fury.io/py/uchr)
[![PyPI downloads](https://img.shields.io/pypi/dm/uchr.svg)](https://pypi.org/project/uchr/)

A powerful command-line tool for searching and exploring Unicode characters, emoji sequences, and character properties.

## 🚀 Features

- **Search by name or meaning**: Find characters by whole words of their Unicode name or, for CJK ideographs, their English meaning
- **Related emoji**: Search also lists emoji with a similar meaning (`ghost` → 👺 goblin, 👹 ogre), ranked by shared CLDR keywords
- **Search by code**: Look up characters by code point or range
- **Search by character**: Reverse lookup from character to details
- **Search by block**: Explore characters within Unicode blocks
- **Emoji support**: Full support for emoji sequences and ZWJ sequences
- **CJK meanings**: CJK ideographs are shown with their English meaning (Unihan kDefinition) in every search
- **Multiple Unicode versions**: Fetch any published version and switch between them
- **Flexible output**: Multiple output formats for different use cases

## 📖 Table of Contents

- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Usage Examples](#-usage-examples)
- [Command Reference](#-command-reference)
- [Database Management](#-database-management)
- [Text Normalization (deprecated)](#-text-normalization)
- [Advanced Examples](#-advanced-examples)
- [Data Sources](#-data-sources)
- [Development](#-development)
- [Contributing](#-contributing)
- [License](#-license)

## 🛠 Installation

### Install from PyPI (Recommended)

```bash
pip install uchr
# or, as an isolated command-line tool with uv
uv tool install uchr
```

### Install from source

```bash
git clone https://github.com/mkyutani/uchr.git
cd uchr
uv tool install .
```

### Initialize database

The database is created automatically on first use of `uchr search`, fetching
the latest Unicode version. To fetch it explicitly instead:

```bash
uchr db update
```

This downloads the latest Unicode data and creates a local SQLite database at:
- Linux/macOS: `~/.local/share/uchr/unicode.db`
- Root users: Automatically chooses between system (`/var/lib/uchr/`) or personal location

The database file is created with mode `0644`: anyone who can reach it can
search it, but only its owner can change it (`db update`/`use`/`delete`).
For the system location this means root.

Multiple Unicode versions can coexist in the same database — see
[Database Management](#-database-management) below.

## ⚡ Quick Start

```bash
# Search for ghost, followed by related emoji such as 👺
uchr search ghost

# Find characters in a code range
uchr search -c 1F47A-1F480

# Search by character
uchr search -x 👻

# Search within a Unicode block
uchr search -b "Emoticons"
```

## 📋 Usage Examples

### Search by Name or Meaning

```bash
uchr search cat
```
```
猫 732B CAT
貓 8C93 CAT
🐈 1F408 CAT
鯴 9BF4 CAT FISH
鲺 9CBA CAT FISH
🐱 1F431 CAT FACE
🐈‍⬛ 1F408 200D 2B1B black cat
...
챁 CC41 HANGUL SYLLABLE CAT
猞 731E A WILD CAT; 猞猁, A LYNX
...
😻 1F63B SMILING CAT FACE WITH HEART-SHAPED EYES
㣇 38C7 A KIND OF BEAST WITH LONG HAIR, OTHER NAME FOR PIG, FOX, WILD CAT, RACCOON
🐯 1F42F TIGER FACE
🐅 1F405 TIGER
🐆 1F406 LEOPARD
```

The expression must match **whole words**, of the character name or, for
CJK ideographs, of their English meaning (Unihan `kDefinition`), which is
shown in place of the name: `cat` finds 猫 (*CAT*) and *HANGUL SYLLABLE
CAT*, but not *INDICATOR* or *CATTLE*. Search also lists **related
emoji**, whose [CLDR keywords](#-data-sources) overlap with those of the
emoji the expression names (🐯 shares *animal* and *cat* with 🐈).

Word matches come first, closest first, then related emoji, most
similar first; ties go in code order:

- **Word matches** rank by the item with the fewest words that matches,
  splitting the meaning, or else the name, into items at `;`, then by the
  length of the whole. So *CAT* alone comes first, then texts with an
  item that is *CAT* itself (䰢 *GHOST; A STAR* after 👻 *GHOST*), then
  *CAT FISH* or *BLACK CAT*, then longer ones, down to 㣇 (*A KIND OF
  BEAST WITH LONG HAIR, …, WILD CAT, RACCOON*). Notes like *(SAME AS 魊)*
  are left out.
- **Related emoji** rank by their cosine similarity of keywords, with
  keywords that many emoji share (like *face*) counting for little; 🐯
  scores 0.64. An emoji that also matches by word, such as 😹 (*CAT FACE
  WITH TEARS OF JOY*), stays with the word matches. The threshold (`-t`)
  only adds or drops related emoji at the end, so it never changes the
  order of the rest.

`-t` sets how close a related emoji must be, from widest to narrowest:
`loose` (similarity 0.2 or more), `normal` (0.3, the default), `close`
(0.5), or any number in (0, 1]. `strict`, the narrowest, is `-s`: the
exact name only, without CJK meanings or related emoji.

```bash
# Only closely related emoji
uchr search ghost -t close

# Exact name only (same as -t strict)
uchr search -s ghost
```

Related emoji need the keyword data that `uchr db update` fetches; until
then, search lists the word matches only and prints a note. Only emoji
have keywords. Emoji newer than the latest CLDR release, and flags and
skin-tone variants (CLDR's derived annotations), have no keywords and are
found by name alone.

### Search by Code Range

```bash
uchr search -c 1F479-1F47B
```
```
👹 1F479 JAPANESE OGRE
👺 1F47A JAPANESE GOBLIN
👻 1F47B GHOST
```

### Search by Character

```bash
uchr search -x 👻
```
```
👻 1F47B GHOST
```

CJK ideographs show their English meaning instead of their name in every
search, and names derived from the code point are spelled out:

```bash
uchr search -x 猫
uchr search -c 17000
```
```
猫 732B CAT
𗀀 17000 TANGUT IDEOGRAPH-17000
```

### Search by Unicode Block

```bash
uchr search -b "Misc_Pictographs"
```

`-b` matches part of a block name, as the UCD abbreviates it
(`Misc_Pictographs`, not *Miscellaneous Symbols and Pictographs*).
`uchr db blocks` lists the names, and emoji sequences by their type,
such as `RGI_Emoji_ZWJ_Sequence`:

```bash
uchr db blocks | grep -i arabic
```
```
Arabic
Arabic_Ext_A
Arabic_Ext_B
Arabic_Ext_C
Arabic_Math
Arabic_PF_A
Arabic_PF_B
Arabic_Sup
```

### Search Without Related Emoji (deprecated)

> **Deprecated:** `-d` will be removed in a future release. The default
> search lists the same matches first, followed by related emoji. It prints
> a warning to stderr when used.

```bash
uchr search -d "pray for happiness"
```
```
祝 795D PRAY FOR HAPPINESS OR BLESSINGS
```

`-d` searches names and CJK meanings for whole words like the default
search, best match first, but leaves out related emoji.

### Output Formatting

```bash
# Simple format (characters only; multiple matches are concatenated)
uchr search goblin -f simple
👺䰨䰪👹👽👻👾🐲🧌👼🧚👿䰦

# UTF-8 format (UTF-8 bytes instead of code points)
uchr search -s "japanese goblin" -f utf8
👺 F09F91BA JAPANESE GOBLIN

# Custom delimiter
uchr search -s "japanese goblin" -D "|"
👺|1F47A|JAPANESE GOBLIN
```

## 🔧 Command Reference

### uchr

Main command with subcommands for all Unicode operations.

#### uchr search

Search Unicode characters with various criteria.

| Option | Short | Description |
|--------|-------|-------------|
| (none) | | Search names and CJK meanings for whole words, plus related emoji (default) |
| `--code` | `-c` | Search by code point or range |
| `--char` | `-x` | Search by character |
| `--block` | `-b` | Search by Unicode block (names: `uchr db blocks`) |
| `--detail` | `-d` | (deprecated) Search names and CJK meanings for whole words, without related emoji |
| `--strict` | `-s` | Exact match (case insensitive), without related emoji |
| `--threshold` | `-t` | How close a related emoji must be: `loose`, `normal` (default), `close`, a minimum similarity in (0, 1], or `strict` (same as `-s`) |
| `--first` | `-1` | Show first result only |
| `--format` | `-f` | Output format: `utf8`, `simple` |
| `--delimiter` | `-D` | Custom delimiter (default: space) |
| `--unicode-version` | | Search a specific Unicode version instead of the current one |

#### uchr normalize (deprecated)

Unicode text normalization and conversion. Deprecated — see
[Text Normalization](#-text-normalization).

| Option | Short | Description |
|--------|-------|-------------|
| `--form` | | Normalization form: `nfc`, `nfd`, `nfkc`, `nfkd` (default: `nfc`) |
| `--halfwidth` | | Convert fullwidth characters to halfwidth |
| `--detail` | | Show detailed binary representation |
| `--compare` | | Show all normalization forms |
| `--delimiter` | | Delimiter for detailed output (default: space) |

#### uchr db

Database management operations. Multiple Unicode versions can be stored in
the database at once; `current_version` (set by `update`/`use`) is what
`search` uses by default.

| Subcommand | Description |
|------------|-------------|
| `uchr db update [--version X.Y.Z] [--verbose]` | Fetch a version (default: latest from unicode.org) and switch to it; `--verbose` lists every skipped code point |
| `uchr db use <version>` | Switch to a version already stored locally, without downloading |
| `uchr db list` | List every version unicode.org currently publishes, marking which are stored locally, current, latest, or draft |
| `uchr db blocks [--version X.Y.Z]` | List the block names of the current (or given) version that `search -b` matches |
| `uchr db delete <version>` | Delete one version's data |
| `uchr db delete --all` | Delete the entire database file |

## 💾 Database Management

The database is created automatically the first time `uchr search` runs
with no local database yet — it fetches the latest Unicode version. There's
no separate "create" step to run manually.

### Fetch a Version

```bash
# Fetch the latest version and make it current
uchr db update

# Fetch a specific version
uchr db update --version 16.0.0
```

A version that is already stored is not downloaded again; `update` just makes
it current. The exception is a version stored as unreleased draft data, which
is fetched again so it picks up changes (or the final release).

`update` also keeps the CLDR emoji keywords behind
[related emoji](#search-by-name) up to date: it looks up the latest CLDR
release on GitHub and downloads its keywords only when that release isn't
stored yet. The keywords are shared by all stored versions. A database
created by an older uchr gets them on its next `uchr db update`. If the
keywords can't be fetched, `update` warns and still succeeds, keeping any
keywords stored before.

### Switch Between Locally Stored Versions

```bash
uchr db use 16.0.0
```

### List Versions

```bash
uchr db list
```

```
4.1.0
5.0.0
...
16.0.0 (local) [157667 chars]
17.0.0 (current) (latest) [162626 chars]
18.0.0 (draft)
```

Versions with no marker are published on unicode.org but not stored locally.

### Search a Specific Version Without Switching

```bash
uchr search ghost --unicode-version 16.0.0
```

If that version isn't stored locally yet, this errors and tells you to run
`uchr db update --version 16.0.0` first — it won't silently download on a
possibly-mistyped version number.

### Remove Data

```bash
# Delete one version's data
uchr db delete 16.0.0

# Wipe the entire database file
uchr db delete --all
```

## 🔤 Text Normalization

> **Deprecated:** `uchr normalize` will be removed in a future release. It
> uses the Unicode data built into Python (`unicodedata.unidata_version`, e.g.
> 15.0.0 on Python 3.12), not the uchr database, so it ignores
> `uchr db` versions. It prints a warning to stderr when used.

The `uchr normalize` command provides Unicode text normalization and conversion utilities.

### Basic Normalization

```bash
# Normalize to NFC (default)
echo "café" | uchr normalize

# Normalize to NFD
echo "café" | uchr normalize --form nfd

# Normalize to NFKC
echo "ﬁle" | uchr normalize --form nfkc

# Normalize to NFKD
echo "ﬁle" | uchr normalize --form nfkd
```

### Text Conversion

```bash
# Convert fullwidth to halfwidth
echo "ＨｅｌｌｏＷｏｒｌｄ" | uchr normalize --halfwidth

# Show detailed binary representation
echo "café" | uchr normalize --detail

# Compare all normalization forms
echo "café" | uchr normalize --compare
```

### Interactive Mode

```bash
# Read from stdin (interactive)
uchr normalize
# Type text and press Ctrl+D to process
```

## 🌟 Advanced Examples

### Finding Emoji Sequences

```bash
# National flags
uchr search -b "RGI_Emoji_Flag_Sequence"

# Family emoji with ZWJ sequences
uchr search family
```

### Terminal Display vs. Browser/Application Support

Many terminals don't properly display complex emoji sequences, but the characters work correctly when copied to browsers or applications.

#### National Flag Example

When searching for flags, you might see separate letters in your terminal:

```bash
uchr search -b "RGI_Emoji_Flag_Sequence" | grep -i norway
```
```
🇳🇴 1F1F3 1F1F4 flag: Norway
```

![Sample to copy Norway's flag in twitter](img/ucsearch-block-flag-norway.png)

Even though you see two separate letters (🇳🇴) in the terminal, when you copy and paste them into a browser or application like Twitter, they combine to display the Norwegian flag 🇳🇴.

![Sample to paste Norway's flag in twitter](img/twitter-norway.png)

#### ZWJ Sequence Example

The same applies to Zero Width Joiner (ZWJ) sequences. Complex emoji like family groups or professional emoji might not render correctly in terminals:

```bash
uchr search "polar bear"
```

In a terminal without proper font support:

![Sample to copy polar bear in twitter](img/ucsearch-polarbear.png)

But when pasted in Twitter or other applications:

![Sample to paste polar bear in twitter](img/twitter-polarbear.png)

> **💡 Tip**: This is expected behavior. The Unicode data is correct, and the characters will work properly in applications that support modern emoji rendering.

### Pipe Operations

```bash
# Get just the character
uchr search -s "japanese goblin" -f simple

# First match only
uchr search snow -1

# Custom format for scripting
uchr search ghost -D "," | cut -d',' -f1
```

### Complex Searches

```bash
# CJK characters with specific meanings
uchr search -d "dragon"

# Characters in multiple blocks
uchr search -b "Mathematical" | head -10
```

## 📚 Data Sources

This tool fetches official Unicode data directly from
[unicode.org](https://www.unicode.org/Public/) — the Unicode Character
Database (`ucdxml`) and Emoji Sequences for whichever version you request
with `uchr db update`. By default it tracks the latest released version;
run `uchr db list` to see everything currently published.

Keywords for [related emoji](#search-by-name) come from the English emoji
annotations of the [Unicode CLDR](https://cldr.unicode.org/) project
(`common/annotations/en.xml` of the latest release in
[unicode-org/cldr](https://github.com/unicode-org/cldr)).

## 🏗 Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management and packaging.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/mkyutani/uchr.git
cd uchr

# Create .venv and install dependencies (from uv.lock)
uv sync

# Run tests
uv run pytest

# Format code
uv run ruff format

# Lint code
uv run ruff check
```

### Building

```bash
uv build
```

### Releasing

Releases are published by GitHub Actions (`.github/workflows/release.yml`).
Bump `version` in `pyproject.toml`, merge it to `main`, then push a matching
tag:

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

The tag must equal `v` + the `pyproject.toml` version, or the build fails.
The workflow then runs the tests, builds the sdist and wheel, publishes them to
[TestPyPI](https://test.pypi.org/project/uchr/), installs the release back
from TestPyPI as a smoke test, waits for approval on the `pypi` environment,
publishes to [PyPI](https://pypi.org/project/uchr/), and creates a GitHub
Release with the built files attached.

Uploads use [Trusted Publishing](https://docs.pypi.org/trusted-publishers/),
so no API tokens are stored in the repository. One-time setup:

1. **PyPI**: in the `uchr` project's *Publishing* settings, add a GitHub
   publisher — owner `mkyutani`, repository `uchr`, workflow `release.yml`,
   environment `pypi`.
2. **TestPyPI**: add the same publisher with environment `testpypi` (as a
   *pending publisher* if the project does not exist there yet).
3. **GitHub**: create the environments `testpypi` and `pypi` under
   *Settings → Environments*. Give `pypi` a required reviewer so the
   production upload waits for approval, and restrict both to `v*` tags.

Tests also run on every pull request and push to `main`
(`.github/workflows/ci.yml`).

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and add tests
4. Run the test suite: `uv run pytest`
5. Format your code: `uv run ruff format`
6. Lint your code: `uv run ruff check`
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

### Code Quality

This project maintains high code quality standards:

- **Type hints**: All functions should include type annotations
- **Testing**: New features should include appropriate tests
- **Documentation**: Update README and docstrings for new features
- **Code style**: Follow Ruff formatting and linting rules

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Unicode Consortium](https://unicode.org/) for maintaining Unicode standards
- [uv](https://docs.astral.sh/uv/) for Python packaging and project management
- Contributors and users of this project

## 📊 Project Status

- **Current Version**: 1.4.0
- **Python Support**: 3.11+
- **Unicode Version**: tracks the latest released version by default; multiple versions can coexist locally (see `uchr db list`)
- **Package Name**: `uchr` (on PyPI)
- **Repository**: [mkyutani/uchr](https://github.com/mkyutani/uchr)

For the latest updates and roadmap, see our [GitHub Issues](https://github.com/mkyutani/uchr/issues).
