package com.smartdoc.user.service.impl;

import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.common.util.HashUtil;
import com.smartdoc.user.dto.*;
import com.smartdoc.user.model.User;
import com.smartdoc.user.repository.UserRepository;
import com.smartdoc.user.security.JwtTokenProvider;
import com.smartdoc.user.service.AuthService;
import io.jsonwebtoken.Claims;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;

/**
 * 认证服务实现。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AuthServiceImpl implements AuthService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider jwtTokenProvider;
    private final StringRedisTemplate redisTemplate;

    /** Redis Key: 黑名单 */
    private static final String BLACKLIST_PREFIX = "session:blacklist:";
    /** Redis Key: Refresh Token */
    private static final String REFRESH_PREFIX = "session:refresh:";

    @Override
    @Transactional
    public LoginResponse register(RegisterRequest request) {
        // 1. 检查用户名是否已存在
        if (userRepository.existsByUsername(request.getUsername())) {
            throw new BusinessException(ErrorCode.USERNAME_EXISTS);
        }

        // 2. 创建用户
        User user = User.builder()
                .username(request.getUsername())
                .passwordHash(passwordEncoder.encode(request.getPassword()))
                .email(request.getEmail())
                .role(User.Role.USER)
                .createdAt(Instant.now())
                .build();
        user = userRepository.save(user);

        log.info("新用户注册: id={}, username={}", user.getId(), user.getUsername());

        // 3. 签发 Token
        return buildLoginResponse(user);
    }

    @Override
    public LoginResponse login(LoginRequest request) {
        // 1. 查找用户
        User user = userRepository.findByUsername(request.getUsername())
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

        // 2. 验证密码
        if (!passwordEncoder.matches(request.getPassword(), user.getPasswordHash())) {
            throw new BusinessException(ErrorCode.PASSWORD_ERROR);
        }

        log.info("用户登录: id={}, username={}", user.getId(), user.getUsername());

        // 3. 签发 Token
        return buildLoginResponse(user);
    }

    @Override
    public LoginResponse refresh(String refreshToken) {
        // 1. 验证 Refresh Token 签名
        Claims claims = jwtTokenProvider.validateToken(refreshToken);
        if (claims == null) {
            throw new BusinessException(ErrorCode.TOKEN_INVALID);
        }

        Long userId = jwtTokenProvider.extractUserId(claims);
        String username = jwtTokenProvider.extractUsername(claims);

        // 2. 检查 Refresh Token 是否在 Redis 中（是否被撤销）
        String redisKey = REFRESH_PREFIX + userId;
        String storedToken = redisTemplate.opsForValue().get(redisKey);
        if (storedToken == null || !storedToken.equals(refreshToken)) {
            throw new BusinessException(ErrorCode.TOKEN_EXPIRED);
        }

        // 3. 生成新的 Access Token（Refresh Token 不变）
        String newAccessToken = jwtTokenProvider.generateAccessToken(userId, username);

        log.info("Token 刷新: userId={}", userId);

        return LoginResponse.builder()
                .accessToken(newAccessToken)
                .refreshToken(refreshToken)
                .userId(userId)
                .username(username)
                .expiresIn(jwtTokenProvider.getAccessExpireMs() / 1000)
                .build();
    }

    @Override
    public void logout(String accessToken) {
        // 1. 验证 Token（即使是登出也要验证，防止恶意请求）
        if (accessToken == null || !accessToken.startsWith("Bearer ")) {
            return; // 格式不对，静默处理
        }
        String token = accessToken.substring(7);

        Claims claims = jwtTokenProvider.validateToken(token);
        if (claims == null) {
            return; // Token 无效，无需加入黑名单
        }

        Long userId = jwtTokenProvider.extractUserId(claims);

        // 2. Access Token 加入黑名单（TTL = Token 剩余有效期）
        long remainingMs = claims.getExpiration().getTime() - System.currentTimeMillis();
        if (remainingMs > 0) {
            String blacklistKey = BLACKLIST_PREFIX + HashUtil.sha256Short(token, 32);
            redisTemplate.opsForValue()
                    .set(blacklistKey, "1", Duration.ofMillis(remainingMs));
        }

        // 3. 删除 Refresh Token（撤销）
        String refreshKey = REFRESH_PREFIX + userId;
        redisTemplate.delete(refreshKey);

        log.info("用户登出: userId={}", userId);
    }

    // ── 私有方法 ──────────────────────────────────────────────

    /** 构建登录/注册响应（包含 Token 对） */
    private LoginResponse buildLoginResponse(User user) {
        String accessToken = jwtTokenProvider.generateAccessToken(
                user.getId(), user.getUsername());
        String refreshToken = jwtTokenProvider.generateRefreshToken(
                user.getId(), user.getUsername());

        // 存储 Refresh Token 到 Redis（Key = userId，方便按用户管理）
        String refreshKey = REFRESH_PREFIX + user.getId();
        Duration refreshTtl = Duration.ofMillis(jwtTokenProvider.getRefreshExpireMs());
        redisTemplate.opsForValue().set(refreshKey, refreshToken, refreshTtl);

        return LoginResponse.builder()
                .accessToken(accessToken)
                .refreshToken(refreshToken)
                .userId(user.getId())
                .username(user.getUsername())
                .role(user.getRole().name())
                .expiresIn(jwtTokenProvider.getAccessExpireMs() / 1000)
                .build();
    }

    // ── 供 Gateway 调用的内部验证方法 ──

    /**
     * 验证 Access Token 并返回 userId，失败返回 null。
     * 此方法给 Gateway JwtAuthFilter 或内部 RPC 使用。
     */
    public Long validateAccessToken(String token) {
        // 检查黑名单
        String blacklistKey = BLACKLIST_PREFIX + HashUtil.sha256Short(token, 32);
        if (Boolean.TRUE.equals(redisTemplate.hasKey(blacklistKey))) {
            log.debug("Token 在黑名单中: {}", blacklistKey);
            return null;
        }

        // 验证 JWT 签名和过期
        return jwtTokenProvider.validateAndGetUserId(token);
    }
}
