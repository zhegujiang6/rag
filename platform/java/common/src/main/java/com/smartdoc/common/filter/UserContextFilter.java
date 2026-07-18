package com.smartdoc.common.filter;

import com.smartdoc.common.context.UserContext;
import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;

import java.io.IOException;

/**
 * 用户上下文过滤器 — 从 HTTP Header 提取当前用户信息。
 *
 * <p>Gateway 在 JWT 鉴权后将 userId/username 写入 Header，
 * 各业务微服务通过此 Filter 提取并设置到 UserContext。
 *
 * <p>需要注册为 Spring Bean（或通过 @WebFilter + @ServletComponentScan）
 */
@Slf4j
public class UserContextFilter implements Filter {

    public static final String HEADER_USER_ID = "X-User-Id";
    public static final String HEADER_USERNAME = "X-Username";

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest httpReq = (HttpServletRequest) request;

        String userIdStr = httpReq.getHeader(HEADER_USER_ID);
        String username = httpReq.getHeader(HEADER_USERNAME);

        if (userIdStr != null && !userIdStr.isBlank()) {
            try {
                Long userId = Long.valueOf(userIdStr);
                UserContext.set(userId, username);
                log.debug("UserContext set: userId={}, username={}", userId, username);
            } catch (NumberFormatException e) {
                log.warn("Invalid X-User-Id header: {}", userIdStr);
            }
        }

        try {
            chain.doFilter(request, response);
        } finally {
            UserContext.clear();
        }
    }
}
