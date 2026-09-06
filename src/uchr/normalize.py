#!/usr/bin/env python3

import sys
import unicodedata


def convert_to_halfwidth(text):
    """Convert fullwidth characters to halfwidth"""
    return "".join(
        chr(ord(char) - 0xFEE0)
        if 0xFF01 <= ord(char) <= 0xFF5E
        else " "
        if char == "　"  # Fullwidth space to regular space
        else char
        for char in text
    )


def get_binary_representation(text):
    """Get binary representation of text as hex string with colon separators"""
    return ":".join(f"{b:02x}" for b in text.encode("utf-8"))


def get_unicode_representation(text):
    """Get Unicode code point representation with colon separators"""
    return ":".join(f"U+{ord(c):04X}" for c in text)


def escape_control_chars(text):
    """Replace control characters and space with dots for display"""
    return "".join("." if ord(char) <= 32 else char for char in text)


def format_detailed_output(text, form, delimiter=" "):
    """Format text with detailed information: result form binary unicode"""
    # Escape control characters in display text
    display_text = escape_control_chars(text)
    binary = get_binary_representation(text)
    unicode_repr = get_unicode_representation(text)
    return delimiter.join([display_text, form, binary, unicode_repr])


def normalize_text(text, form="NFC", halfwidth=False):
    """Normalize text using specified Unicode normalization form and halfwidth conversion"""
    # Apply Unicode normalization
    normalized = (
        unicodedata.normalize(form.upper(), text)
        if form.upper() in ["NFC", "NFD", "NFKC", "NFKD"]
        else text
    )

    # Apply halfwidth conversion if specified
    return convert_to_halfwidth(normalized) if halfwidth else normalized


def analyze_normalization(content, delimiter=" "):
    """Analyze text and show all normalization forms in consistent format"""
    forms = ["Original", "NFC", "NFD", "NFKC", "NFKD"]

    for form in forms:
        if form == "Original":
            result_text = content
        else:
            result_text = unicodedata.normalize(form, content)

        print(format_detailed_output(result_text, form, delimiter))


def normalize_command(
    form="NFC",
    halfwidth=False,
    compare=False,
    detailed=False,
    delimiter=" ",
    input_file=None,
):
    """Main normalize command function"""
    try:
        # Read entire content as single string
        if input_file and input_file != "-":
            with open(input_file, encoding="utf-8") as f:
                content = f.read().rstrip("\n")
        else:
            content = sys.stdin.read().rstrip("\n")

        # Process content
        if compare:
            analyze_normalization(content, delimiter)
        else:
            result = normalize_text(content, form=form, halfwidth=halfwidth)
            if detailed:
                # Determine actual form used
                actual_form = form.upper()
                if halfwidth:
                    actual_form += "+HALFWIDTH"
                print(format_detailed_output(result, actual_form, delimiter))
            else:
                print(
                    result, end=""
                )  # Don't add extra newline since content may already have it

    except FileNotFoundError:
        print(f"Error: File '{input_file}' not found", file=sys.stderr)
        return 1
    except UnicodeDecodeError:
        print("Error: Unable to decode file as UTF-8", file=sys.stderr)
        return 1
    except BrokenPipeError:
        # Handle pipe operations gracefully
        pass

    return 0
