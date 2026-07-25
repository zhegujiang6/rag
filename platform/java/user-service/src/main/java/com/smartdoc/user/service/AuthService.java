package com.smartdoc.user.service;

import com.smartdoc.user.dto.LoginRequest;
import com.smartdoc.user.dto.LoginResponse;
import com.smartdoc.user.dto.RegisterRequest;

/**
 * 认证服务接口。
 */
public interface AuthService {

    /**
     * 用户注册。
     *
     * @return 包含 AccessToken + RefreshToken 的响应
     */
    LoginResponse register(RegisterRequest request);

    /**
     * 用户登录 (用户名 + 密码 → JWT)。
     */
    LoginResponse login(LoginRequest request);

    /**
     * 刷新 Access Token (用 Refresh Token)。
     */
    LoginResponse refresh(String refreshToken);

    /**
     * 登出 — 将 Access Token 加入 Redis 黑名单。
     */
    void logout(String accessToken);
}
