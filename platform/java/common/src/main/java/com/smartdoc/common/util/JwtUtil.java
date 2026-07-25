package com.smartdoc.common.util;

import io.jsonwebtoken.*;
import io.jsonwebtoken.security.Keys;
import lombok.extern.slf4j.Slf4j;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.Map;

/**
 * JWT 工具类 — Token 生成、验证、解析。
 * <p>使用 HMAC-SHA256 签名算法。
 */
@Slf4j
public final class JwtUtil {

    private JwtUtil() {}

    /** 默认密钥 (生产环境应从 Nacos 配置中心读取) */
    private static final String DEFAULT_SECRET = "smart-doc-search-jwt-secret-key-2024-min-length-32";

    /** Access Token 有效期: 15 分钟 */
    public static final long ACCESS_EXPIRE_MS = 15 * 60 * 1000L;

    /** Refresh Token 有效期: 7 天 */
    public static final long REFRESH_EXPIRE_MS = 7 * 24 * 60 * 60 * 1000L;

    /**
     * 生成 Access Token。
     *
     * @param userId   用户 ID
     * @param username 用户名
     * @param secret   签名密钥 (Base64)
     */
    public static String generateAccessToken(Long userId, String username, String secret) {
        return generateToken(userId, username, secret, ACCESS_EXPIRE_MS);
    }

    /**
     * 生成 Refresh Token。
     */
    public static String generateRefreshToken(Long userId, String username, String secret) {
        return generateToken(userId, username, secret, REFRESH_EXPIRE_MS);
    }

    /**
     * 生成指定有效期的 Token。
     *
     * @param userId   用户 ID
     * @param username 用户名
     * @param secret   签名密钥
     * @param expireMs 有效期（毫秒）
     */
    public static String generateToken(Long userId, String username, String secret, long expireMs) {
        SecretKey key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        Date now = new Date();
        return Jwts.builder()
                .subject(String.valueOf(userId))
                .claim("username", username)
                .issuedAt(now)
                .expiration(new Date(now.getTime() + expireMs))
                .signWith(key)
                .compact();
    }

    /**
     * 验证 Token 并返回 Claims。
     *
     * @return null 表示验证失败
     */
    public static Claims validateToken(String token, String secret) {
        try {
            SecretKey key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
            return Jwts.parser()
                    .verifyWith(key)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
        } catch (JwtException e) {
            log.warn("JWT 验证失败: {}", e.getMessage());
            return null;
        }
    }

    /** 从 Claims 提取用户 ID */
    public static Long getUserId(Claims claims) {
        return Long.valueOf(claims.getSubject());
    }

    /** 从 Claims 提取用户名 */
    public static String getUsername(Claims claims) {
        return claims.get("username", String.class);
    }
}
