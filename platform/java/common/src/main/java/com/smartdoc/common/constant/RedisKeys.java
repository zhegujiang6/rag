package com.smartdoc.common.constant;

/**
 * Redis Key 命名规范 — 统一管理，避免硬编码。
 *
 * <p>命名格式: {业务域}:{子域}:{标识}
 */
public final class RedisKeys {

    private RedisKeys() {}

    // ── 查询缓存 ──
    /** RAG 检索结果缓存 (Hash → 结果JSON) */
    public static final String RAG_CACHE = "rag:cache:";

    /** Embedding 向量缓存 (文本哈希 → 向量JSON) */
    public static final String EMBED_CACHE = "rag:embed:";

    // ── 会话 ──
    /** JWT Access Token 存储 */
    public static final String SESSION_TOKEN = "session:token:";

    /** Token 黑名单 (登出后加入) */
    public static final String SESSION_BLACKLIST = "session:blacklist:";

    /** 用户 Refresh Token */
    public static final String SESSION_REFRESH = "session:refresh:";

    // ── 限流 ──
    /** 用户级别限流 (userId:api) */
    public static final String RATE_LIMIT_USER = "ratelimit:user:";

    /** IP 级别限流 */
    public static final String RATE_LIMIT_IP = "ratelimit:ip:";

    // ── 任务队列 ──
    /** 文档处理任务队列 (List) */
    public static final String QUEUE_DOC_PROCESS = "queue:doc:process";

    // ── 统计 ──
    /** 热点查询 Top-K (ZSet) */
    public static final String STATS_HOT_QUERIES = "stats:hot:queries";

    /** BM25 索引重建锁 */
    public static final String LOCK_BM25_REBUILD = "lock:bm25:";

    // ── 配置缓存 ──
    /** Nacos 配置本地缓存 */
    public static final String CONFIG_CACHE = "config:";

    // ── 工具方法 ──

    public static String ragCacheKey(String queryHash) {
        return RAG_CACHE + queryHash;
    }

    public static String embedCacheKey(String textHash) {
        return EMBED_CACHE + textHash;
    }

    public static String sessionTokenKey(String token) {
        return SESSION_TOKEN + token;
    }

    public static String blacklistKey(String token) {
        return SESSION_BLACKLIST + token;
    }

    public static String rateLimitUserKey(Long userId, String api) {
        return RATE_LIMIT_USER + userId + ":" + api;
    }

    public static String bm25LockKey(Long kbId) {
        return LOCK_BM25_REBUILD + kbId;
    }
}
