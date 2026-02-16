# Background Indexing Implementation Spec

**Status:** DRAFT  
**Phase:** Layer 2 - Phase 3  
**Priority:** #3 (after batch embedding + cache)  
**Author:** Byte  
**Date:** 2026-02-15

---

## Problem

Large reindex operations block the CLI:
- **100k records** takes ~5-10 minutes to reindex
- User must wait for completion (no progress visibility)
- Cannot cancel if started by mistake
- Blocks other database operations during reindex

**Example:** User accidentally runs `kameleondb embeddings reindex --all` on production DB with 500k records → 30+ minute wait, no way to cancel.

---

## Solution Overview

Async reindex with progress tracking:
1. Start reindex in background thread
2. Return immediately with job ID
3. Status command shows progress
4. Cancel command stops in-flight job

---

## Architecture

### Job State Management

**New Table: kdb_reindex_jobs**

```sql
CREATE TABLE kdb_reindex_jobs (
    job_id VARCHAR(36) PRIMARY KEY,
    entity_name VARCHAR(255),           -- NULL = all entities
    status VARCHAR(20) NOT NULL,        -- pending, running, completed, failed, cancelled
    total_records INTEGER,              -- Total records to process
    processed_records INTEGER DEFAULT 0,-- Records processed so far
    error_message TEXT,                 -- Error details if failed
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    INDEX idx_jobs_status (status, created_at)
);
```

**Status values:**
- `pending`: Job queued, not started yet
- `running`: Actively processing
- `completed`: Finished successfully
- `failed`: Error occurred
- `cancelled`: User cancelled

---

## API Design

### SearchEngine Methods

```python
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

class SearchEngine:
    def __init__(self, engine, embedding_provider=None):
        # ... existing init ...
        self._executor = ThreadPoolExecutor(max_workers=1)  # Single reindex thread
        self._active_jobs: dict[str, Future] = {}
    
    def reindex_background(
        self,
        entity: str | None = None,
    ) -> str:
        """Start background reindex and return job ID.
        
        Args:
            entity: Entity to reindex, or None for all entities
        
        Returns:
            Job ID for tracking progress
        """
        job_id = str(uuid4())
        
        # Create job record
        with Session(self._engine) as session:
            session.execute(
                text("""
                    INSERT INTO kdb_reindex_jobs (job_id, entity_name, status)
                    VALUES (:job_id, :entity, 'pending')
                """),
                {"job_id": job_id, "entity": entity},
            )
            session.commit()
        
        # Submit background task
        future = self._executor.submit(self._run_reindex_job, job_id, entity)
        self._active_jobs[job_id] = future
        
        return job_id
    
    def _run_reindex_job(
        self,
        job_id: str,
        entity: str | None,
    ) -> None:
        """Execute reindex in background thread."""
        try:
            # Mark as running
            with Session(self._engine) as session:
                # Count total records
                if entity:
                    result = session.execute(
                        text("SELECT COUNT(*) FROM kdb_records WHERE entity_name = :entity"),
                        {"entity": entity},
                    ).scalar()
                else:
                    result = session.execute(
                        text("SELECT COUNT(*) FROM kdb_records"),
                    ).scalar()
                total = result or 0
                
                session.execute(
                    text("""
                        UPDATE kdb_reindex_jobs
                        SET status = 'running', total_records = :total, started_at = NOW()
                        WHERE job_id = :job_id
                    """),
                    {"job_id": job_id, "total": total},
                )
                session.commit()
            
            # Perform reindex in batches with progress updates
            batch_size = 100
            processed = 0
            
            while True:
                # Check if cancelled
                if self._is_job_cancelled(job_id):
                    self._mark_job_cancelled(job_id, processed)
                    return
                
                # Fetch next batch
                with Session(self._engine) as session:
                    if entity:
                        records = session.execute(
                            text("""
                                SELECT entity_name, id, data
                                FROM kdb_records
                                WHERE entity_name = :entity
                                LIMIT :limit OFFSET :offset
                            """),
                            {"entity": entity, "limit": batch_size, "offset": processed},
                        ).fetchall()
                    else:
                        records = session.execute(
                            text("""
                                SELECT entity_name, id, data
                                FROM kdb_records
                                LIMIT :limit OFFSET :offset
                            """),
                            {"limit": batch_size, "offset": processed},
                        ).fetchall()
                
                if not records:
                    break
                
                # Index batch
                batch_records = [
                    (r[0], r[1], self._extract_content(r[2]))
                    for r in records
                ]
                self.index_records_batch(batch_records)
                
                processed += len(records)
                
                # Update progress
                with Session(self._engine) as session:
                    session.execute(
                        text("""
                            UPDATE kdb_reindex_jobs
                            SET processed_records = :processed
                            WHERE job_id = :job_id
                        """),
                        {"job_id": job_id, "processed": processed},
                    )
                    session.commit()
            
            # Mark completed
            with Session(self._engine) as session:
                session.execute(
                    text("""
                        UPDATE kdb_reindex_jobs
                        SET status = 'completed', completed_at = NOW()
                        WHERE job_id = :job_id
                    """),
                    {"job_id": job_id},
                )
                session.commit()
        
        except Exception as e:
            # Mark failed
            with Session(self._engine) as session:
                session.execute(
                    text("""
                        UPDATE kdb_reindex_jobs
                        SET status = 'failed', error_message = :error, completed_at = NOW()
                        WHERE job_id = :job_id
                    """),
                    {"job_id": job_id, "error": str(e)},
                )
                session.commit()
        finally:
            # Clean up
            self._active_jobs.pop(job_id, None)
    
    def get_job_status(self, job_id: str) -> dict | None:
        """Get status of background job."""
        with Session(self._engine) as session:
            result = session.execute(
                text("""
                    SELECT entity_name, status, total_records, processed_records,
                           error_message, created_at, started_at, completed_at
                    FROM kdb_reindex_jobs
                    WHERE job_id = :job_id
                """),
                {"job_id": job_id},
            ).fetchone()
            
            if not result:
                return None
            
            return {
                "job_id": job_id,
                "entity": result[0],
                "status": result[1],
                "total": result[2],
                "processed": result[3],
                "error": result[4],
                "created_at": result[5],
                "started_at": result[6],
                "completed_at": result[7],
                "progress_pct": (result[3] / result[2] * 100) if result[2] else 0,
            }
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        with Session(self._engine) as session:
            # Check if job is running
            result = session.execute(
                text("SELECT status FROM kdb_reindex_jobs WHERE job_id = :job_id"),
                {"job_id": job_id},
            ).scalar()
            
            if result not in ("pending", "running"):
                return False
            
            # Mark for cancellation
            session.execute(
                text("""
                    UPDATE kdb_reindex_jobs
                    SET status = 'cancelled', completed_at = NOW()
                    WHERE job_id = :job_id
                """),
                {"job_id": job_id},
            )
            session.commit()
            return True
    
    def _is_job_cancelled(self, job_id: str) -> bool:
        """Check if job has been cancelled."""
        with Session(self._engine) as session:
            status = session.execute(
                text("SELECT status FROM kdb_reindex_jobs WHERE job_id = :job_id"),
                {"job_id": job_id},
            ).scalar()
            return status == "cancelled"
```

---

## CLI Commands

```bash
# Start background reindex
$ kameleondb embeddings reindex --background
Started background reindex (job: a3f2c9b1-...)
Use 'kameleondb embeddings status' to check progress

# Start reindex for specific entity
$ kameleondb embeddings reindex Contact --background
Started background reindex of Contact (job: b4e3d0c2-...)

# Check status
$ kameleondb embeddings status
Job ID: a3f2c9b1-4d5e-6f7g-8h9i-0j1k2l3m4n5o
Entity: (all)
Status: running
Progress: 45,231 / 100,000 (45.2%)
Started: 2026-02-15 18:30:15
Elapsed: 2m 34s
ETA: 3m 12s

# List all jobs
$ kameleondb embeddings jobs --limit 5
Job ID                                Entity   Status     Progress    Started
a3f2c9b1-4d5e-6f7g-8h9i-0j1k2l3m4n5o  (all)    running    45.2%       2m ago
f5e4d3c2-b1a0-9f8e-7d6c-5b4a3c2d1e0f  Contact  completed  100%        1h ago
c2d1e0f9-8g7h-6i5j-4k3l-2m1n0o9p8q7r  Product  failed     23%         2h ago

# Cancel running job
$ kameleondb embeddings cancel a3f2c9b1-4d5e-6f7g-8h9i-0j1k2l3m4n5o
Cancelled job a3f2c9b1-... (processed 45,231 / 100,000)

# Clean up old job records
$ kameleondb embeddings jobs --clean --older-than 7d
Removed 23 job records older than 7 days
```

---

## Progress Display

### Terminal UI (Rich/tqdm-style)

```
Reindexing Contact...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 45,231/100,000  45%  [2:34<3:12]  292 rec/s
```

**Elements:**
- Progress bar (visual)
- Current / Total
- Percentage
- Elapsed time < ETA
- Records per second

---

## Performance Considerations

### Threading vs Multiprocessing

**Choice: Threading**
- Pro: Simpler state sharing (same DB connection pool)
- Pro: Lower overhead for I/O-bound operations
- Con: GIL limits CPU parallelism

**Why it works:**
- Reindex is I/O-bound (embedding API calls, DB writes)
- Single reindex thread prevents resource contention
- Batch API + cache handle parallelism within each batch

### Batch Size Tuning

**Default: 100 records**
- Small enough for responsive cancellation (<10s latency)
- Large enough for batch API efficiency
- Progress updates every ~0.5-2 seconds

---

## Error Handling

### Transient Failures

**Strategy:** Retry individual batches
```python
for attempt in range(3):
    try:
        self.index_records_batch(batch_records)
        break
    except Exception as e:
        if attempt == 2:
            raise
        time.sleep(2 ** attempt)  # Exponential backoff
```

### Fatal Failures

**Mark job as failed:**
- Preserve error message in job record
- Allow user to inspect and retry
- CLI shows last error in status

---

## Testing Strategy

### Unit Tests
- `test_reindex_background_returns_job_id()`
- `test_job_status_shows_progress()`
- `test_cancel_running_job()`
- `test_completed_job_not_cancellable()`

### Integration Tests
- Background reindex 1000 records
- Cancel midway through
- Multiple concurrent jobs (should queue)

### Performance Tests
- 100k record reindex completes in <10 minutes
- Progress updates every <2 seconds
- Cancel latency <10 seconds

---

## Migration Strategy

### Schema Migration

Add to `migrations.py`:

```python
def migration_003_reindex_jobs(engine: Engine) -> None:
    """Add reindex job tracking table."""
    with Session(engine) as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS kdb_reindex_jobs (
                job_id VARCHAR(36) PRIMARY KEY,
                entity_name VARCHAR(255),
                status VARCHAR(20) NOT NULL,
                total_records INTEGER,
                processed_records INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_jobs_status
            ON kdb_reindex_jobs (status, created_at)
        """))
        session.commit()
```

---

## Implementation Plan

### Phase 1: Core Background Execution (2-3 hours)
1. Add `kdb_reindex_jobs` table migration
2. Implement `reindex_background()` and `_run_reindex_job()`
3. Add `get_job_status()` method
4. Unit tests for job lifecycle

### Phase 2: CLI Integration (1-2 hours)
1. Add `--background` flag to `embeddings reindex`
2. Implement `embeddings status` command
3. Implement `embeddings jobs` command
4. Progress display formatting

### Phase 3: Cancellation & Cleanup (1 hour)
1. Implement `cancel_job()` method
2. Add `embeddings cancel` command
3. Job cleanup logic (old completed jobs)

**Total estimate: 4-6 hours**

---

## Success Metrics

- [ ] 100k record reindex runs in background without blocking CLI
- [ ] Progress updates visible every <2 seconds
- [ ] Cancel latency <10 seconds
- [ ] Job history retained for debugging

---

## Future Enhancements

### Multi-threading (Phase 4?)
- Process multiple entities in parallel
- Requires connection pool tuning
- Complexity: moderate

### Webhook Notifications (Phase 4?)
- POST to webhook on job completion
- Useful for CI/CD integration
- Complexity: low

---

## Next Steps

1. **Get approval** - Review with Marcos
2. **Implement after batch + cache** - Background indexing depends on batch API
3. **Test at scale** - Validate with 100k+ record databases

---

## References

- Phase 3 Plan: `docs/layer2-phase3-plan.md`
- Batch Embedding Spec: `docs/batch-embedding-spec.md`
- SearchEngine: `src/kameleondb/search/engine.py`
