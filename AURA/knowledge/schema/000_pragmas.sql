-- Execute on every connection: WAL mode + performance pragmas
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = 10000;           -- ~40MB page cache
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;        -- 256MB memory-mapped I/O
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;          -- 5s timeout on locked DB
