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
is the source packaged and used for vectorization. For timestamped uploads,
the original PDF, OCR output, cleaned Markdown, job progress, and manifest are
versioned together when the upload is ready to deploy.

## Updating documents

Use the admin workflow to upload, extract, review OCR, clean, and review the
Markdown. The workflow displays seven persisted steps: upload, render, OCR,
normalize, chunk, embed, and catalog sync. **Sync version này vào vector DB**
embeds the reviewed version and updates the local route catalog; it can change
the Chroma store configured for that environment. Do not sync to production
just to inspect OCR or clean output.

Before deploying, commit the reviewed timestamp directory and the matching
`routes.json` change. The upload creates a pending route; it is not available
to chat until the version sync succeeds. After deployment, run **Sync catalog
vào vector DB** in the production admin page to index the committed routes in
the persistent production Chroma store. This production sync does not write
back to the source repository.

Do not put generated Chroma data here. Chroma is stored separately in its
persistent volume. Keep source paths in `routes.json` relative, inside this
directory, and aligned with the directory containing the corresponding
version.
