package com.smartdoc.gateway.filter;

import com.smartdoc.common.util.HashUtil;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * JWT 鉴权全局过滤器 (Gateway 层)。
 *
 * <p>流程：
 * <ol>
 *   <li>白名单路径直接放行</li>
 *   <li>从 Authorization Header 提取 Bearer Token</li>
 *   <li>验证 JWT 签名和过期</li>
 *   <li>检查 Redis 黑名单（登出后的 Token）</li>
 *   <li>将 userId/username 写入 X-User-Id / X-Username Header 传给下游</li>
 * </ol>
 */
@Slf4j
@Component
public class JwtAuthFilter implements GlobalFilter, Ordered {

    @Value("${jwt.secret:smart-doc-search-jwt-secret-key-2024-min-length-32}")
    private String jwtSecret;

    private final ReactiveStringRedisTemplate redisTemplate;

    public JwtAuthFilter(ReactiveStringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /** 白名单 — 无需认证 */
    private static final List<String> WHITELIST = List.of(
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/refresh"
    );

    /** 黑名单 Redis Key 前缀 */
    private static final String BLACKLIST_PREFIX = "session:blacklist:";

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String path = exchange.getRequest().getURI().getPath();

        // ── 1. 白名单直接放行 ──
        if (isWhitelisted(path)) {
            return chain.filter(exchange);
        }

        // ── 2. 提取 Token ──
        String authHeader = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            return unauthorized(exchange, "缺少认证 Token");
        }
        String token = authHeader.substring(7);

        // ── 3. 验证 JWT 签名 + 过期 ──
        Claims claims;
        try {
            SecretKey key = Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8));
            claims = Jwts.parser()
                    .verifyWith(key)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
        } catch (JwtException e) {
            log.warn("JWT 验证失败: {} — {}", e.getMessage(), path);
            return unauthorized(exchange, "Token 无效或已过期");
        }

        Long userId = Long.valueOf(claims.getSubject());
        String username = claims.get("username", String.class);

        // ── 4. 检查 Redis 黑名单 ──
        String blacklistKey = BLACKLIST_PREFIX + HashUtil.sha256Short(token, 32);
        return redisTemplate.hasKey(blacklistKey)
                .flatMap(isBlacklisted -> {
                    if (Boolean.TRUE.equals(isBlacklisted)) {
                        log.debug("Token 在黑名单中: userId={}", userId);
                        return unauthorized(exchange, "Token 已登出");
                    }

                    // ── 5. 放行，注入用户信息到 Header ──
                    ServerWebExchange mutatedExchange = exchange.mutate()
                            .request(r -> r
                                    .header("X-User-Id", String.valueOf(userId))
                                    .header("X-Username", username != null ? username : "")
                            )
                            .build();

                    log.debug("JWT 鉴权通过: userId={}, username={}, path={}",
                            userId, username, path);

                    return chain.filter(mutatedExchange);
                });
    }

    @Override
    public int getOrder() {
        return -100;
    }

    // ── 辅助方法 ──────────────────────────────────────────────

    private boolean isWhitelisted(String path) {
        return WHITELIST.stream().anyMatch(path::startsWith);
    }

    private Mono<Void> unauthorized(ServerWebExchange exchange, String message) {
        exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
        exchange.getResponse().getHeaders().setContentType(MediaType.APPLICATION_JSON);
        String body = String.format(
                "{\"code\":2001,\"message\":\"%s\",\"data\":null}", message);
        DataBuffer buffer = exchange.getResponse()
                .bufferFactory().wrap(body.getBytes(StandardCharsets.UTF_8));
        return exchange.getResponse().writeWith(Mono.just(buffer));
    }
}
