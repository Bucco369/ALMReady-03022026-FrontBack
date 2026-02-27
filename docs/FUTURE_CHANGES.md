# Future Changes

## Session Storage Growth

### Current Behavior
- Sessions live in `backend/data/sessions/{uuid}/`
- Per-session storage: ~100MB (two Parquets + JSONs)
- TTL configurable via `SESSION_TTL_DAYS` env var (default: 7 days)
- Cleanup runs at startup + every 6 hours via background task
- Extracted CSVs and uploaded ZIP are deleted immediately after parsing

### Implemented
- **Post-parse cleanup**: CSVs + ZIP deleted after successful parsing (`balance_parser.py`)
- **Configurable TTL**: `SESSION_TTL_DAYS` environment variable (`main.py`)
- **Periodic cleanup**: Background `asyncio` task runs every 6h (`main.py`)
- **DataFrame cache invalidation**: Stale sessions evicted from in-memory cache during cleanup

### Remaining Improvements
1. **LRU-style expiration**: Add `last_accessed_at` to `SessionMeta`, update it on every API call, and clean up based on inactivity rather than creation date
2. **Disk budget**: Set a max total storage limit (e.g., 2GB) and evict oldest sessions when exceeded

### Long-Term (Multi-User / Production)
3. **Per-user session isolation**: Tie sessions to authenticated users so cleanup is scoped
4. **Object storage**: Move large files (Parquets, uploads) to S3/GCS with signed URLs, keeping only metadata on local disk
5. **Database-backed sessions**: Replace file-based sessions with a proper DB (PostgreSQL) for metadata + S3 for blobs
