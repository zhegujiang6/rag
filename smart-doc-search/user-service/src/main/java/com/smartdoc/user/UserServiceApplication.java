package com.smartdoc.user;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

/**
 * 用户服务入口。
 *
 * <p>职责：
 * <ul>
 *   <li>用户注册/登录（BCrypt + JWT）</li>
 *   <li>Token 签发与刷新</li>
 *   <li>角色权限管理 (RBAC: admin / user / viewer)</li>
 *   <li>会话管理（Redis 存储 Token）</li>
 *   <li>API Key 管理（第三方集成）</li>
 * </ul>
 *
 * <p>API 端点：
 * <pre>
 *   POST /api/v1/auth/register   — 注册
 *   POST /api/v1/auth/login      — 登录
 *   POST /api/v1/auth/refresh    — 刷新 Token
 *   POST /api/v1/auth/logout     — 登出
 *   GET  /api/v1/users/me        — 当前用户信息
 * </pre>
 */
@SpringBootApplication(scanBasePackages = {"com.smartdoc.user", "com.smartdoc.common"})
@EnableDiscoveryClient
public class UserServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(UserServiceApplication.class, args);
    }
}
