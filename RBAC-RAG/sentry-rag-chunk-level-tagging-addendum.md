# Sentry RAG — chunk-level role tagging (addendum)

Right now every chunk of a document just inherits the document's chosen roles. This
addendum changes that: at upload, the AI suggests a role subset **per chunk** (never
outside the document's chosen roles), and an admin must review and publish before
those chunks go live.

## What changes

- Chunk `allowed_roles` is no longer a straight copy of the document's roles — it's now
  a per-chunk value that starts as an AI suggestion and can be edited by an admin.
- Documents get a review/publish gate: a newly uploaded document is not retrievable by
  regular users until an admin confirms its chunk-level tags.

## Data model changes

```
documents   + status ('pending_review' | 'published', default 'pending_review')
chunks      + roles_ai_suggested (boolean, default true)
```

`chunks.allowed_roles` already exists — this only changes how it gets populated and
who can edit it.

## Upload flow (revised)

1. Admin selects the document's roles as before (e.g. `hr`, `admin`) — this set is now
   a **ceiling**: the AI can only choose from within it, never add a role outside it.
2. Backend chunks + embeds as before.
3. **One LLM call** (batch all chunks into a single prompt; split into a few batches
   only if the document is long enough to blow the context window — never one call per
   chunk, to stay inside the free-tier rate limit) proposes a role subset for every
   chunk. Default is the full candidate set; the model narrows a chunk only when it
   contains something clearly more sensitive than the rest of the document — e.g. a
   named individual's pay, health, discipline, or legal detail sitting inside an
   otherwise general-audience doc.
4. Store the suggestion on each chunk (`roles_ai_suggested = true`). Document status =
   `pending_review`. The document is **not retrievable by non-admin queries yet.**
5. Admin opens a chunk review screen for that document: each chunk shows a text
   preview, its current (suggested) roles as an editable multi-select, and an
   "AI-suggested" badge. Editing a chunk's roles clears the badge for that chunk.
6. Admin clicks **Save & publish**. Whatever roles are on each chunk at that moment
   (accepted or edited) become final. Document status → `published`, now queryable
   normally under the existing RBAC filter.

**Fail-closed on failure:** if the suggestion call errors, times out, or returns
something malformed (missing chunks, a role outside the candidate set), fall back to
the full candidate set for the affected chunk(s) — never guess, never block the
upload itself.

## Backend

- `nim_client`: new `suggest_chunk_roles(chunks, candidate_roles)` — one prompt,
  numbered chunks, ask for strict JSON:
  `{"chunk_roles": [{"index": 0, "roles": ["employee","hr"]}, ...]}`.
  Validate every returned role is inside `candidate_roles`; anything else falls back
  per the rule above.
- Query endpoint: add `documents.status = 'published'` to the existing role-filtered
  retrieval. Admin's unfiltered bypass still includes `pending_review` documents too —
  admin already sees everything, and being able to query a doc while reviewing it is
  useful, not a leak.
- New endpoints:
  - `GET /admin/documents/{id}/chunks` — chunk previews + current roles +
    `roles_ai_suggested` flag.
  - `PATCH /admin/documents/{id}/chunks/{chunk_id}` — edit one chunk's roles (clears
    its `roles_ai_suggested` flag).
  - `POST /admin/documents/{id}/publish` — flips status to `published`.
  - `POST /admin/documents/{id}/reset-chunk-roles` — bulk-resets every chunk back to
    the document's candidate role set (undo button for a bad review pass).

## Frontend (admin console)

- Document list: a status badge per document (`Pending review` / `Published`).
- New chunk review view (modal or sub-page), opened from a document row: chunk list
  with preview text, editable role multi-select, "AI-suggested" badge, and the
  "Save & publish" action.
- "Reset to document defaults" bulk action in the same view.
- Non-admin experience is unchanged — they still only ever see the chat interface.

## Explicitly out of scope

- No manual chunk creation/splitting UI — chunking itself stays automatic, same as
  today, only the role assignment per chunk is new.
- No automatic re-suggestion after publish — editing a chunk's roles post-publish is
  just the existing "edit tags" flow, now applied per chunk instead of per document.
