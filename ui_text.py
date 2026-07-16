from __future__ import annotations


def section(title: str, emoji: str = '✦') -> str:
    return f'{emoji} <b>{title}</b>'


def stat(label: str, value: object, emoji: str) -> str:
    return f'{emoji} <b>{label}:</b> {value}'


def divider() -> str:
    return '━━━━━━━━━━━━━━'


def compact_block(*lines: str) -> str:
    return '\n'.join(line for line in lines if line is not None)
