# Visual melody editor: next implementation

The current ABC sketchpad remains a prototype. It is not the intended final composing experience.

## Existing open-source candidate

Smoosic is a browser music notation application with visual editing, instrument playback, MIDI/MusicXML import and export, and a library mode. Its current documentation links to integration examples:

- Project and feature list: https://smoosic.github.io/Smoosic/
- Source: https://github.com/Smoosic/Smoosic
- Embedding and conversion examples: https://github.com/Smoosic/Demos
- Editor demo: https://smoosic.github.io/Smoosic/release/html/smoosic.html

The Demos README describes a single `domContainer` configuration, a mouse-pitch selection feature, an async update example, and MusicXML loading/conversion examples. The demo repository is MIT-licensed; inspect the pinned main package, font, sample, and engraving-library licences when vendoring the full editor. Source documentation was checked on 17 October 2026. This is research, not a tested integration.

## Evaluate before replacing the sketchpad

1. Embed a pinned build behind a small melody-only adapter; hide orchestration controls. Keep one staff and one voice initially.
2. Verify mouse/keyboard entry, note selection, rests, accidentals, ties, undo/redo, measures, lyric underlay, and keyboard accessibility.
3. Round-trip a score through the native serialized format without losing stable note identifiers. Preserve MusicXML import/export for portability. Existing ABC tunes need an explicit conversion path and retained original source.
4. Connect score changes to the same revision-aware autosave service. Never replace a collaborator's newer score silently.
5. Attach discussions to stable measure/note IDs plus a score revision, rather than just ABC character positions.
6. Test sample loading, offline behaviour, browser playback, mobile layout, and printing.

If the existing editor cannot meet these needs, a reusable melody-editor package could be developed as a separate project. Give it a small API (`load`, `serialize`, change events, selection events, playback) and keep accounts, approvals, and comments in this website. BarMaker now provides the short-phrase performance-to-ABC part as an independent local repository in `BarMaker/`. It uses abcjs and Pitchy, rather than implementing a full notation editor. The full-score editor evaluation above remains future work; no upstream project has been modified.
