"""The terminal shows a model's thinking labelled and set apart, never read as markup."""

from __future__ import annotations

from rich.console import Console

from babo.cli import terminal


def test_thinking_is_labelled_and_brackets_in_it_are_kept(monkeypatch) -> None:
    out = Console(record=True, width=120, force_terminal=False)
    monkeypatch.setattr(terminal, "console", out)
    terminal._print_cli_reasoning("Check [the board] first.", None)  # pyright: ignore[reportPrivateUsage]
    assert out.export_text() == "[thinking]\nCheck [the board] first.\n[/thinking]\n"


def test_thinking_that_streams_in_pieces_is_one_labelled_block(monkeypatch) -> None:
    out = Console(record=True, width=120, force_terminal=False)
    monkeypatch.setattr(terminal, "console", out)
    buffer = terminal._ReasoningBuffer()  # pyright: ignore[reportPrivateUsage]
    for piece in ["U is up.\n", "F is front.\n", "So north is up"]:
        text = buffer.add(piece)
        if text:
            terminal._print_cli_reasoning(text, None, None, buffer)  # pyright: ignore[reportPrivateUsage]
    terminal._flush_cli_reasoning(buffer, None)  # pyright: ignore[reportPrivateUsage]
    assert out.export_text() == "[thinking]\nU is up.\nF is front.\nSo north is up\n[/thinking]\n"
    terminal._flush_cli_reasoning(buffer, None)  # pyright: ignore[reportPrivateUsage]  # nothing open: nothing more
    assert out.export_text() == ""
