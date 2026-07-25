package com.smartdoc.user.security;

import com.smartdoc.common.util.JwtUtil;
import io.jsonwebtoken.Claims;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * JWT Token 提供者 — 封装 JwtUtil，从配置读取密钥和有效期。
 */
@Slf4j
@Component
public class JwtTokenProvider {

    @Getter
    @Value("${jwt.secret:smart-doc-search-jwt-secret-key-2024-min-length-32}")
    private String secret;

    @Getter
    @Value("${jwt.access-expire-ms:900000}")
    private long accessExpireMs;

    @Getter
    @Value("${jwt.refresh-expire-ms:604800000}")
    private long refreshExpireMs;

    /** 生成 Access Token */
    public String generateAccessToken(Long userId, String username) {
        return JwtUtil.generateToken(userId, username, secret, accessExpireMs);
    }

    /** 生成 Refresh Token */
    public String generateRefreshToken(Long userId, String username) {
        return JwtUtil.generateToken(userId, username, secret, refreshExpireMs);
    }

    /** 验证 Token 并返回 Claims，失败返回 null */
    public Claims validateToken(String token) {
        return JwtUtil.validateToken(token, secret);
    }

    /** 从 Claims 提取用户 ID */
    public Long extractUserId(Claims claims) {
        return JwtUtil.getUserId(claims);
    }

    /** 从 Claims 提取用户名 */
    public String extractUsername(Claims claims) {
        return JwtUtil.getUsername(claims);
    }

    /** 验证 Token 并返回用户 ID，失败返回 null */
    public Long validateAndGetUserId(String token) {
        Claims claims = validateToken(token);
        return claims != null ? extractUserId(claims) : null;
    }
}
