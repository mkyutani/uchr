# Unicode Tools (uchr)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Unicode](https://img.shields.io/badge/Unicode-multi--version-green.svg)](https://unicode.org/)
[![PyPI version](https://badge.fury.io/py/uchr.svg)](https://badge.fury.io/py/uchr)
[![PyPI downloads](https://img.shields.io/pypi/dm/uchr.svg)](https://pypi.org/project/uchr/)

A powerful command-line tool for searching and exploring Unicode characters, emoji sequences, and character properties.

## 🚀 Features

- **Search by name**: Find characters by their Unicode name
- **Search by code**: Look up characters by code point or range
- **Search by character**: Reverse lookup from character to details
- **Search by block**: Explore characters within Unicode blocks
- **Emoji support**: Full support for emoji sequences and ZWJ sequences
- **CJK details**: Enhanced descriptions for CJK characters using kDefinition
- **Flexible output**: Multiple output formats for different use cases
- **Text normalization**: Unicode normalization and text conversion utilities

## 📖 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Examples](#usage-examples)
- [Command Reference](#command-reference)
- [Database Management](#database-management)
- [Text Normalization](#text-normalization)
- [Contributing](#contributing)
- [License](#license)

## 🛠 Installation

### Install from PyPI (Recommended)

```bash
pip install uchr
```

### Install from source

```bash
git clone https://github.com/mkyutani/uchr.git
cd uchr
poetry install
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
[Database Management](#database-management) below.

## ⚡ Quick Start

```bash
# Search for ghost-related characters
uchr search ghost

# Find characters in a code range
uchr search -c 1F47A-1F480

# Search by character
uchr search -x 👻

# Search within a Unicode block
uchr search -b "Emoticons"
```

## 📋 Usage Examples

### Search by Name

```bash
uchr search goblin
```
```
👺 1F47A JAPANESE GOBLIN
```

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

### Search by Unicode Block

```bash
uchr search -b "Misc_Pictographs"
```

### Search with Details (CJK Characters)

```bash
uchr search -d "pray for happiness"
```
```
祝 795D CJK UNIFIED IDEOGRAPH-#; PRAY FOR HAPPINESS OR BLESSINGS
```

### Output Formatting

```bash
# Simple format (characters only)
uchr search ghost -f simple
👻

# UTF-8 format
uchr search ghost -f utf8
👻 F0 9F 91 BB GHOST

# Custom delimiter
uchr search ghost -D "|"
👻|1F47B|GHOST
```

## 🔧 Command Reference

### uchr

Main command with subcommands for all Unicode operations.

#### uchr search

Search Unicode characters with various criteria.

| Option | Short | Description |
|--------|-------|-------------|
| `--name` | | Search by character name (default) |
| `--code` | `-c` | Search by code point or range |
| `--char` | `-x` | Search by character |
| `--block` | `-b` | Search by Unicode block |
| `--detail` | `-d` | Search in character details |
| `--strict` | `-s` | Exact match (case insensitive) |
| `--first` | `-1` | Show first result only |
| `--format` | `-f` | Output format: `utf8`, `simple` |
| `--delimiter` | `-D` | Custom delimiter (default: space) |
| `--unicode-version` | | Search a specific Unicode version instead of the current one |

#### uchr normalize (deprecated)

Unicode text normalization and conversion. Deprecated — see
[Text Normalization](#text-normalization).

| Option | Short | Description |
|--------|-------|-------------|
| `--form` | `-f` | Normalization form: `nfc`, `nfd`, `nfkc`, `nfkd` |
| `--halfwidth` | | Convert fullwidth characters to halfwidth |
| `--detail` | | Show detailed binary representation |
| `--compare` | | Show all normalization forms |

#### uchr db

Database management operations. Multiple Unicode versions can be stored in
the database at once; `current_version` (set by `update`/`use`) is what
`search` uses by default.

| Subcommand | Description |
|------------|-------------|
| `uchr db update [--version X.Y.Z]` | Fetch a version (default: latest from unicode.org) and switch to it |
| `uchr db use <version>` | Switch to a version already stored locally, without downloading |
| `uchr db list` | List every version unicode.org currently publishes, marking which are stored locally, current, latest, or draft |
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

### Switch Between Locally Stored Versions

```bash
uchr db use 16.0.0
```

### List Versions

```bash
uchr db list
```

```
15.0.0
16.0.0 (local) [157667 chars]
17.0.0 (current) (latest) [162626 chars]
18.0.0 (draft)
```

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
uchr search ghost -f simple

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

## 🏗 Data Sources

This tool fetches official Unicode data directly from
[unicode.org](https://www.unicode.org/Public/) — the Unicode Character
Database (`ucdxml`) and Emoji Sequences for whichever version you request
with `uchr db update`. By default it tracks the latest released version;
run `uchr db list` to see everything currently published.

## 🏗 Development

This project uses [Poetry](https://python-poetry.org/) for dependency management and packaging.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/mkyutani/uchr.git
cd uchr

# Install dependencies
poetry install

# Run tests
poetry run pytest

# Format code
poetry run black src/

# Lint code
poetry run ruff check src/
```

### Building

```bash
poetry build
```

### Releasing

Releases are published by GitHub Actions (`.github/workflows/release.yml`).
Bump `version` in `pyproject.toml`, merge it to `main`, then push a matching
tag:

```bash
git tag v1.0.0
git push origin v1.0.0
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
4. Run the test suite: `poetry run pytest`
5. Format your code: `poetry run black src/`
6. Lint your code: `poetry run ruff check src/`
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

### Code Quality

This project maintains high code quality standards:

- **Type hints**: All functions should include type annotations
- **Testing**: New features should include appropriate tests
- **Documentation**: Update README and docstrings for new features
- **Code style**: Follow Black formatting and Ruff linting rules

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Unicode Consortium](https://unicode.org/) for maintaining Unicode standards
- [Poetry](https://python-poetry.org/) for modern Python packaging
- Contributors and users of this project

## 📊 Project Status

- **Current Version**: 0.3.0
- **Python Support**: 3.8+
- **Unicode Version**: tracks the latest released version by default; multiple versions can coexist locally (see `uchr db list`)
- **Package Name**: `uchr` (on PyPI)
- **Repository**: [mkyutani/uchr](https://github.com/mkyutani/uchr)

For the latest updates and roadmap, see our [GitHub Issues](https://github.com/mkyutani/uchr/issues).
