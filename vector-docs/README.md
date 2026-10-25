# Vector documents

This directory contains the source files used to build the chatbot's document
catalog. Keep route configuration at the root; permanent source documents use
a stable slug, while each new admin upload gets a timestamp-named folder.

```text
vector-docs/
|-- README.md
|-- routes.json
`-- documents/
    |-- qd3266/
    |   `-- current/
    |       |-- source.pdf
    |       |-- ocr.txt
    |       `-- clean.md
    |-- qd2748-2019/
    |   `-- archive/
    |       `-- source.pdf
    `-- <YYYYMMDDHHMMSS-xxxxxx>/
        |-- <original-upload-filename>.pdf
        |-- ocr.txt
        |-- clean.md
        |-- job.json
        `-- manifest.json
```

## File roles

- `routes.json` maps chat routes to Chroma collections and document source paths.
  Source paths are relative to this directory.
- `documents/qd3266/current/` holds the reviewed default QĐ 3266 source: the
  original PDF, raw OCR, and normalized Markdown used for vectorization.
- `documents/<timestamp-id>/` stores each staged admin upload. The timestamp ID
  is generated when the admin uploads; the original PDF filename is preserved.
  OCR, cleaned Markdown, and ingest metadata stay beside it.
- Historical documents that are not active routes live in their own
  `documents/<slug>/archive/` directory.

The QĐ 3266 `source.pdf` and `ocr.txt` remain Git-ignored as before; `clean.md`
is the source packaged and used for vectorization.

## Updating documents

Use the admin workflow to upload, extract, review/clean, and sync a document.
Commit the reviewed timestamp directory and the matching `routes.json` change
before deploying. After deployment, run **Sync catalog vào vector DB** in the
admin page to index the committed sources in persistent Chroma.

Do not put generated Chroma data here. Chroma is stored separately in its
persistent volume. Keep source paths in `routes.json` relative, inside this
directory, and aligned with the directory containing the corresponding
version.
