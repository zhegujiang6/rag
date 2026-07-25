package com.smartdoc.common.context;

/**
 * 用户上下文 — 基于 ThreadLocal，在请求生命周期内持有当前用户信息。
 *
 * <p>由 Gateway JwtAuthFilter 将 userId/username 写入 Header，
 * 各微服务通过拦截器/过滤器从中提取并设置到 UserContext。
 *
 * <p>用法：
 * <pre>{@code
 *   Long userId = UserContext.getUserId();
 *   String username = UserContext.getUsername();
 * }</pre>
 */
public final class UserContext {

    private static final ThreadLocal<Long> USER_ID = new ThreadLocal<>();
    private static final ThreadLocal<String> USERNAME = new ThreadLocal<>();

    private UserContext() {}

    public static void set(Long userId, String username) {
        USER_ID.set(userId);
        USERNAME.set(username);
    }

    public static Long getUserId() {
        return USER_ID.get();
    }

    public static String getUsername() {
        return USERNAME.get();
    }

    public static void clear() {
        USER_ID.remove();
        USERNAME.remove();
    }
}
