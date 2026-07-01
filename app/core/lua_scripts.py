"""
All 4 rate-limiting Lua scripts.

Each script receives:
  KEYS[1]  — Redis key prefix (algorithm-specific key names are derived inside)
  ARGV[1]  — limit (integer)
  ARGV[2]  — window_seconds (integer)
  ARGV[3]  — now_seconds (Unix seconds, from Redis TIME — never server clock)
  ARGV[4]  — now_microseconds (Unix microseconds, from Redis TIME)
  ARGV[5]  — burst_multiplier (float, e.g. "1.5"; capacity = limit * burst_multiplier)
  ARGV[6]  — unique_id (UUID string — prevents ZADD collision in sliding window)

Each script returns a Redis array: {allowed, remaining, reset_at, retry_after}
  allowed      — 1 if request passes, 0 if blocked
  remaining    — tokens/requests left after this one
  reset_at     — Unix timestamp when the window/bucket fully resets
  retry_after  — seconds until the next request can succeed (0 if allowed)
"""

FIXED_WINDOW_SCRIPT = """
local key      = KEYS[1]
local limit    = tonumber(ARGV[1])
local window   = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])

-- Align window boundary: floor(now / window) * window + window
local boundary = math.floor(now / window) * window + window
local ttl      = boundary - now

local count = redis.call('INCR', key)
if count == 1 then
    -- EXPIREAT on first increment so boundary is exact regardless of when
    redis.call('EXPIREAT', key, boundary)
end

local allowed, remaining, retry_after
if count <= limit then
    allowed       = 1
    remaining     = limit - count
    retry_after   = 0
else
    allowed       = 0
    remaining     = 0
    retry_after   = ttl
    -- Decrement so blocked requests don't inflate the counter
    redis.call('DECR', key)
end

return {allowed, remaining, boundary, retry_after}
"""

SLIDING_WINDOW_SCRIPT = """
local key           = KEYS[1]
local limit         = tonumber(ARGV[1])
local window        = tonumber(ARGV[2])
local now_sec       = tonumber(ARGV[3])
local now_usec      = tonumber(ARGV[4])
local unique_id     = ARGV[6]

-- Remove entries older than the window
local cutoff = now_usec - (window * 1000000)
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

local count = redis.call('ZCARD', key)

local allowed, remaining, reset_at, retry_after
if count < limit then
    -- Score = microsecond timestamp; member = usec:uuid to prevent collision
    local member = now_usec .. ':' .. unique_id
    redis.call('ZADD', key, now_usec, member)
    redis.call('EXPIRE', key, window + 1)
    allowed      = 1
    remaining    = limit - count - 1
    reset_at     = now_sec + window
    retry_after  = 0
else
    allowed      = 0
    remaining    = 0
    -- Oldest entry in the window tells us when a slot opens
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    if oldest[2] then
        local oldest_usec = tonumber(oldest[2])
        retry_after = math.ceil((oldest_usec + window * 1000000 - now_usec) / 1000000)
        reset_at    = now_sec + retry_after
    else
        retry_after = window
        reset_at    = now_sec + window
    end
end

return {allowed, remaining, reset_at, retry_after}
"""

TOKEN_BUCKET_SCRIPT = """
local key             = KEYS[1]
local capacity        = math.floor(tonumber(ARGV[1]) * tonumber(ARGV[5]))
local rate            = tonumber(ARGV[1]) / tonumber(ARGV[2])   -- tokens per second
local now             = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens      = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    -- First request: full bucket
    tokens      = capacity
    last_refill = now
end

-- Refill tokens based on elapsed time
local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + elapsed * rate)

local allowed, remaining, reset_at, retry_after
if tokens >= 1 then
    tokens       = tokens - 1
    allowed      = 1
    remaining    = math.floor(tokens)
    reset_at     = now + math.ceil((capacity - tokens) / rate)
    retry_after  = 0
else
    allowed      = 0
    remaining    = 0
    -- Time to wait for 1 token
    retry_after  = math.ceil((1 - tokens) / rate)
    reset_at     = now + retry_after
end

-- Persist state; expire slightly beyond the full refill time
local expire_secs = math.ceil(capacity / rate) + 1
redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
redis.call('EXPIRE', key, expire_secs)

return {allowed, remaining, reset_at, retry_after}
"""

LEAKY_BUCKET_SCRIPT = """
local key        = KEYS[1]
local capacity   = tonumber(ARGV[1])
local rate       = tonumber(ARGV[1]) / tonumber(ARGV[2])   -- leaks per second
local now        = tonumber(ARGV[3])

local data       = redis.call('HMGET', key, 'queue_size', 'last_leak')
local queue_size = tonumber(data[1])
local last_leak  = tonumber(data[2])

if queue_size == nil then
    queue_size = 0
    last_leak  = now
end

-- Drain the queue proportional to elapsed time
local elapsed = math.max(0, now - last_leak)
local leaked  = math.floor(elapsed * rate)
queue_size    = math.max(0, queue_size - leaked)
if leaked > 0 then
    last_leak = now
end

local allowed, remaining, reset_at, retry_after
if queue_size < capacity then
    queue_size   = queue_size + 1
    allowed      = 1
    remaining    = capacity - queue_size
    reset_at     = now + math.ceil(queue_size / rate)
    retry_after  = 0
else
    allowed      = 0
    remaining    = 0
    retry_after  = math.ceil(1 / rate)
    reset_at     = now + retry_after
end

local expire_secs = math.ceil(capacity / rate) + 1
redis.call('HMSET', key, 'queue_size', queue_size, 'last_leak', last_leak)
redis.call('EXPIRE', key, expire_secs)

return {allowed, remaining, reset_at, retry_after}
"""

# Maps algorithm name to its Lua source
LUA_SCRIPTS: dict[str, str] = {
    "fixed_window":   FIXED_WINDOW_SCRIPT,
    "sliding_window": SLIDING_WINDOW_SCRIPT,
    "token_bucket":   TOKEN_BUCKET_SCRIPT,
    "leaky_bucket":   LEAKY_BUCKET_SCRIPT,
}
